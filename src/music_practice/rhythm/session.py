"""Streaming rhythm session: emit one closed note at a time (docs/05)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from music_practice.pitch.config import PitchDetectConfig
from music_practice.pitch.detector import pitch_track_from_audio
from music_practice.rhythm.config import OnsetDetectConfig, RhythmJudgeConfig
from music_practice.rhythm.judge import ExpectedNote, RhythmSegment, judge_notes
from music_practice.rhythm.onset import detect_onsets_audio
from music_practice.start_detect.frame import AudioFrame


@dataclass
class RhythmSession:
    """Incremental rhythm judge over PCM frames.

    ``push`` appends audio and returns a :class:`RhythmSegment` only when a note
    has just been **closed**. Most pushes return ``None``. Extra closed notes
    from the same update are drained via ``poll``.

    A note closes when the following expected note has an assigned onset within
    onset tolerance (avoids closing on far false peaks). ``flush`` closes any
    remainder with a final full-buffer judgement.
    """

    _tempo_bpm: float = 120.0
    _sample_rate: int = 22050
    _expected: list[ExpectedNote] = field(default_factory=list)
    _judge_config: RhythmJudgeConfig = field(default_factory=RhythmJudgeConfig)
    _onset_config: OnsetDetectConfig | None = None
    _pcm: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.float32))
    _emitted: int = 0
    _queue: list[RhythmSegment] = field(default_factory=list)
    _closed: bool = False
    _last_onset_count: int = -1
    _cached_segs: list[RhythmSegment] | None = None

    @classmethod
    def open(
        cls,
        expected_notes: Sequence[ExpectedNote],
        *,
        tempo_bpm: float = 120.0,
        sample_rate: int = 22050,
        judge_config: RhythmJudgeConfig | None = None,
        onset_config: OnsetDetectConfig | None = None,
    ) -> RhythmSession:
        sounding = [n for n in expected_notes if not n.is_rest]
        if not sounding:
            raise ValueError("expected_notes has no sounding notes")
        tempo = float(tempo_bpm) if tempo_bpm > 0 else 120.0
        return cls(
            _tempo_bpm=tempo,
            _sample_rate=int(sample_rate),
            _expected=list(sounding),
            _judge_config=judge_config or RhythmJudgeConfig(),
            _onset_config=onset_config or OnsetDetectConfig.for_tempo(tempo),
        )

    @property
    def tempo_bpm(self) -> float:
        return self._tempo_bpm

    @property
    def buffer_sec(self) -> float:
        if self._sample_rate <= 0:
            return 0.0
        return float(self._pcm.shape[0]) / float(self._sample_rate)

    @property
    def emitted_count(self) -> int:
        return self._emitted

    @property
    def expected_count(self) -> int:
        return len(self._expected)

    def push(self, frame: AudioFrame) -> RhythmSegment | None:
        """Append one PCM packet; return a segment only if a note just closed."""
        if self._closed:
            return self.poll()

        if frame.sample_rate != self._sample_rate:
            raise ValueError(
                f"sample_rate mismatch: session={self._sample_rate} frame={frame.sample_rate}"
            )
        if frame.sample_count <= 0:
            return self.poll()

        self._pcm = np.concatenate([self._pcm, frame.pcm])
        self._update_closed_notes(final=False)
        return self.poll()

    def poll(self) -> RhythmSegment | None:
        """Return next queued closed-note result, if any."""
        if not self._queue:
            return None
        return self._queue.pop(0)

    def flush(self) -> list[RhythmSegment]:
        """Close remaining notes with a final full-buffer judgement."""
        if not self._closed:
            self._cached_segs = None
            self._update_closed_notes(final=True)
            self._closed = True
        out = list(self._queue)
        self._queue.clear()
        return out

    def final_segments(self) -> list[RhythmSegment]:
        """Authoritative judgement on the full buffer so far (batch-equivalent)."""
        return self._judge_buffer()

    def _update_closed_notes(self, *, final: bool) -> None:
        if self._emitted >= len(self._expected):
            return
        ocfg = self._onset_config or OnsetDetectConfig.for_tempo(self._tempo_bpm)
        if self._pcm.size < ocfg.frame_size:
            return

        tau = self._judge_config.onset_tolerance_sec(self._tempo_bpm)

        # Onset-only probe is cheaper than pyin; skip full judge until the buffer
        # reaches the next expected note (or flush).
        if not final:
            if self._emitted + 1 >= len(self._expected):
                return
            next_exp = self._expected[self._emitted + 1].onset_sec
            if self.buffer_sec < next_exp:
                return

        onsets = detect_onsets_audio(
            self._pcm,
            sample_rate=self._sample_rate,
            config=ocfg,
            tempo=self._tempo_bpm,
        )
        if (
            not final
            and len(onsets) == self._last_onset_count
            and self._cached_segs is not None
        ):
            segs = self._cached_segs
        else:
            self._last_onset_count = len(onsets)
            segs = self._judge_buffer(precomputed_onsets=onsets)
            self._cached_segs = segs

        while self._emitted < len(segs):
            i = self._emitted
            seg = segs[i]
            if not final:
                if i + 1 >= len(segs):
                    break
                nxt = segs[i + 1]
                if nxt.onset_detected_sec is None or seg.onset_detected_sec is None:
                    break
                next_exp = self._expected[i + 1].onset_sec
                # Require the *next* assigned onset to land near the next expected
                # note — otherwise a false peak would prematurely close this note.
                if abs(float(nxt.onset_detected_sec) - next_exp) > tau:
                    break
                if self.buffer_sec < float(nxt.onset_detected_sec) + 0.01:
                    break
                if self.buffer_sec < next_exp:
                    break
            self._queue.append(seg)
            self._emitted += 1

    def _judge_buffer(
        self, *, precomputed_onsets: list[float] | None = None
    ) -> list[RhythmSegment]:
        ocfg = self._onset_config or OnsetDetectConfig.for_tempo(self._tempo_bpm)
        onsets = (
            list(precomputed_onsets)
            if precomputed_onsets is not None
            else detect_onsets_audio(
                self._pcm,
                sample_rate=self._sample_rate,
                config=ocfg,
                tempo=self._tempo_bpm,
            )
        )
        pitch_cfg = PitchDetectConfig.for_tempo(
            self._tempo_bpm, sample_rate=self._sample_rate
        )
        track = pitch_track_from_audio(self._pcm, pitch_cfg)
        return judge_notes(
            self._expected,
            onsets,
            track,
            tempo_bpm=self._tempo_bpm,
            config=self._judge_config,
        )
