"""Streaming start detection over concatenated PCM frames."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Literal

import numpy as np
from music2seq.features.pitch_extractor import PitchSequence
from music2seq.matcher.global_match import GlobalMatchConfig
from music2seq.template.store import load_template
from music2seq.types import NoteEvent

from music_practice.models import Score
from music_practice.start_detect.context import StartDetectContext, StartDetectResult
from music_practice.start_detect.detector import detect_start_audio, prepare_template_window
from music_practice.start_detect.frame import AudioFrame
from music_practice.start_detect.mapping import resolve_template_id
from music_practice.types import StartNoteRef

SessionState = Literal["idle", "listening", "started", "timed_out", "closed"]


class StartDetectSession:
    """Receive continuous PCM frames, concatenate, and run narrow-window DTW."""

    def __init__(self) -> None:
        self._state: SessionState = "idle"
        self._score: Score | None = None
        self._start_note: StartNoteRef | None = None
        self._template_id: str | None = None
        self._context = StartDetectContext()
        self._template_sec: float | None = None
        self._note_events: list[NoteEvent] = []
        self._cfg: GlobalMatchConfig | None = None
        self._local_template: PitchSequence | None = None
        self._offset_center_frame: int = 0
        self._sample_rate: int = 22050
        self._pcm = np.zeros(0, dtype=np.float32)
        self._open_mono: float | None = None
        self._last_dtw_mono: float | None = None
        self._last_result: StartDetectResult | None = None
        self._expected_seq: int = 0
        self._last_frame_samples: int = 0
        self._last_t0_sec: float | None = None
        self._gap_fill_samples: int = 0

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def buffer_sec(self) -> float:
        if self._sample_rate <= 0:
            return 0.0
        return float(self._pcm.shape[0]) / float(self._sample_rate)

    def open(
        self,
        score: Score,
        *,
        start_note: StartNoteRef,
        templates_dir: str | Path,
        template_id: str | None = None,
        score_template_map: str | Path | None = None,
        context: StartDetectContext | None = None,
        sample_rate: int = 22050,
    ) -> StartDetectResult:
        ctx = context or StartDetectContext()
        tid = resolve_template_id(
            score.score_id,
            template_id=template_id,
            map_path=score_template_map,
        )
        package = load_template(tid, templates_dir=Path(templates_dir))
        template_sec, note_events, cfg, local_template, offset = prepare_template_window(
            package,
            start_note,
            context=ctx,
        )
        self._state = "listening"
        self._score = score
        self._start_note = start_note
        self._template_id = tid
        self._context = ctx
        self._template_sec = template_sec
        self._note_events = note_events
        self._cfg = cfg
        self._local_template = local_template
        self._offset_center_frame = offset
        self._sample_rate = sample_rate
        self._pcm = np.zeros(0, dtype=np.float32)
        self._open_mono = time.monotonic()
        self._last_dtw_mono = None
        self._expected_seq = 0
        self._last_frame_samples = 0
        self._last_t0_sec = None
        self._gap_fill_samples = 0
        self._last_result = StartDetectResult(
            start_note=start_note,
            started=False,
            timed_out=False,
            wait_elapsed_sec=0.0,
            wait_timeout_sec=ctx.wait_timeout_sec,
            template_sec=template_sec,
            query_duration_sec=0.0,
            extra={"template_id": tid, "score_id": score.score_id, "state": self._state},
        )
        return self._last_result

    def push(self, frame: AudioFrame) -> StartDetectResult:
        if self._state == "idle":
            raise RuntimeError("StartDetectSession 未 open")
        if self._state in {"started", "timed_out", "closed"}:
            assert self._last_result is not None
            return self._last_result
        if frame.sample_rate != self._sample_rate:
            raise ValueError(
                f"sample_rate 不一致: frame={frame.sample_rate}, session={self._sample_rate}"
            )
        if frame.seq < self._expected_seq:
            # drop late / duplicate packets
            return self._evaluate()

        gap_samples = self._gap_fill_for(frame)
        if gap_samples > 0:
            self._pcm = np.concatenate(
                [self._pcm, np.zeros(gap_samples, dtype=np.float32)]
            )
            self._gap_fill_samples += gap_samples

        self._expected_seq = frame.seq + 1
        self._last_frame_samples = frame.sample_count
        if frame.t0_sec is not None:
            self._last_t0_sec = frame.t0_sec + frame.duration_sec
        self._pcm = np.concatenate([self._pcm, frame.pcm])
        return self._evaluate()

    def poll(self) -> StartDetectResult:
        """Advance wall-clock wait without new PCM (e.g. App paused / heartbeat)."""
        if self._state == "idle":
            raise RuntimeError("StartDetectSession 未 open")
        if self._state in {"started", "timed_out", "closed"}:
            assert self._last_result is not None
            return self._last_result
        return self._evaluate()

    def close(self) -> StartDetectResult:
        if self._last_result is None:
            raise RuntimeError("StartDetectSession 未 open")
        if self._state == "listening":
            self._state = "closed"
            self._last_result.extra["state"] = self._state
        return self._last_result

    def _gap_fill_for(self, frame: AudioFrame) -> int:
        """Insert silence samples for missing seq / time gaps."""
        if frame.seq <= self._expected_seq:
            return 0
        missing = frame.seq - self._expected_seq
        # Prefer time-based pad when t0_sec is available
        if frame.t0_sec is not None and self._last_t0_sec is not None:
            gap_sec = max(0.0, frame.t0_sec - self._last_t0_sec)
            return int(round(gap_sec * self._sample_rate))
        # Fallback: assume each missing packet ≈ current/last frame size
        packet = frame.sample_count or self._last_frame_samples
        if packet <= 0:
            packet = max(1, int(round(self._sample_rate / 256)))
        return int(missing * packet)

    def _evaluate(self) -> StartDetectResult:
        elapsed = self._elapsed_sec()
        if elapsed >= self._context.wait_timeout_sec:
            self._state = "timed_out"
            self._last_result = StartDetectResult(
                start_note=self._start_note,  # type: ignore[arg-type]
                started=False,
                timed_out=True,
                wait_elapsed_sec=elapsed,
                wait_timeout_sec=self._context.wait_timeout_sec,
                template_sec=self._template_sec,
                query_duration_sec=self._sliding_window_sec(),
                extra={
                    "template_id": self._template_id,
                    "score_id": self._score.score_id if self._score else None,
                    "state": self._state,
                    "buffer_sec": self.buffer_sec,
                    "gap_fill_samples": self._gap_fill_samples,
                },
            )
            return self._last_result

        window_pcm = self._sliding_window_pcm()
        window_sec = window_pcm.shape[0] / float(self._sample_rate)
        if window_sec < self._context.min_query_sec:
            self._last_result = StartDetectResult(
                start_note=self._start_note,  # type: ignore[arg-type]
                started=False,
                timed_out=False,
                wait_elapsed_sec=elapsed,
                wait_timeout_sec=self._context.wait_timeout_sec,
                template_sec=self._template_sec,
                query_duration_sec=window_sec,
                extra={
                    "template_id": self._template_id,
                    "score_id": self._score.score_id if self._score else None,
                    "state": self._state,
                    "buffer_sec": self.buffer_sec,
                    "gap_fill_samples": self._gap_fill_samples,
                    "reason": "buffer_too_short",
                },
            )
            return self._last_result

        if not self._should_run_dtw():
            assert self._last_result is not None
            self._last_result.wait_elapsed_sec = elapsed
            self._last_result.extra["buffer_sec"] = self.buffer_sec
            self._last_result.extra["gap_fill_samples"] = self._gap_fill_samples
            return self._last_result

        self._last_dtw_mono = time.monotonic()
        result = detect_start_audio(
            self._score,  # type: ignore[arg-type]
            start_note=self._start_note,  # type: ignore[arg-type]
            query_pcm=window_pcm,
            sample_rate=self._sample_rate,
            template_sec=self._template_sec,  # type: ignore[arg-type]
            note_events=self._note_events,
            cfg=self._cfg,  # type: ignore[arg-type]
            local_template=self._local_template,  # type: ignore[arg-type]
            offset_center_frame=self._offset_center_frame,
            template_id=self._template_id or "",
            context=self._context,
        )
        result.wait_elapsed_sec = elapsed
        result.extra["state"] = self._state
        result.extra["buffer_sec"] = self.buffer_sec
        result.extra["query_window_sec"] = self._context.max_query_sec
        result.extra["gap_fill_samples"] = self._gap_fill_samples
        result.extra["score_id"] = self._score.score_id if self._score else None
        self._last_result = result
        if result.started:
            self._state = "started"
            result.extra["state"] = self._state
        return result

    def _elapsed_sec(self) -> float:
        if self._open_mono is None:
            return 0.0
        return time.monotonic() - self._open_mono

    def _sliding_window_samples(self) -> int:
        return max(1, int(round(self._context.max_query_sec * self._sample_rate)))

    def _sliding_window_pcm(self) -> np.ndarray:
        n = self._sliding_window_samples()
        if self._pcm.shape[0] <= n:
            return self._pcm
        return self._pcm[-n:]

    def _sliding_window_sec(self) -> float:
        return float(self._sliding_window_pcm().shape[0]) / float(self._sample_rate)

    def _should_run_dtw(self) -> bool:
        if self._last_dtw_mono is None:
            return True
        return (time.monotonic() - self._last_dtw_mono) >= self._context.dtw_interval_sec
