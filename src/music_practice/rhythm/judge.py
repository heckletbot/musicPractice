"""Rhythm judgement: onset_ok ∧ duration_ok (docs/05 §6.3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Sequence

from music_practice.pitch.detector import PitchTrack
from music_practice.rhythm.config import RhythmJudgeConfig
from music_practice.rhythm.duration import DurationMeasure, measure_duration

TimingResult = Literal["CORRECT", "ONSET_ERROR", "DURATION_ERROR", "BOTH_ERROR"]


@dataclass
class ExpectedNote:
    """One expected sounded note on the practice timeline (onset 0 = start note)."""

    onset_sec: float
    duration_sec: float
    pitch_midi: float
    measure: int | None = None
    note_index_in_measure: int | None = None
    is_rest: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "onset_sec": self.onset_sec,
            "duration_sec": self.duration_sec,
            "pitch_midi": self.pitch_midi,
            "measure": self.measure,
            "note_index_in_measure": self.note_index_in_measure,
            "is_rest": self.is_rest,
        }


@dataclass
class RhythmSegment:
    note_ref: dict[str, Any] | None
    onset_detected_sec: float | None
    onset_expected_sec: float
    onset_error_sec: float | None
    onset_ok: bool
    duration_detected_sec: float
    duration_expected_sec: float
    duration_ratio: float | None
    duration_ok: bool
    duration_mode: str
    rhythm_ok: bool
    timing_result: TimingResult
    valid_frame_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "note_ref": self.note_ref,
            "onset_detected_sec": self.onset_detected_sec,
            "onset_expected_sec": self.onset_expected_sec,
            "onset_error_sec": self.onset_error_sec,
            "onset_ok": self.onset_ok,
            "duration_detected_sec": self.duration_detected_sec,
            "duration_expected_sec": self.duration_expected_sec,
            "duration_ratio": self.duration_ratio,
            "duration_ok": self.duration_ok,
            "duration_mode": self.duration_mode,
            "rhythm_ok": self.rhythm_ok,
            "timing_result": self.timing_result,
            "valid_frame_count": self.valid_frame_count,
        }


def _timing_result(onset_ok: bool, duration_ok: bool) -> TimingResult:
    """Fine-grained label. Product pass/fail uses ``rhythm_ok`` (= duration_ok)."""
    if duration_ok and onset_ok:
        return "CORRECT"
    if duration_ok and not onset_ok:
        # Duration passed: still rhythm_ok; keep ONSET_ERROR as diagnostic only.
        return "ONSET_ERROR"
    if not onset_ok and not duration_ok:
        return "BOTH_ERROR"
    return "DURATION_ERROR"


def _assign_onsets(
    expected: Sequence[ExpectedNote],
    detected_onsets: Sequence[float],
) -> list[float | None]:
    """Greedy nearest-neighbor assignment in time order."""
    remaining = sorted(float(t) for t in detected_onsets)
    assigned: list[float | None] = []
    for note in expected:
        if note.is_rest:
            assigned.append(None)
            continue
        if not remaining:
            assigned.append(None)
            continue
        best_i = min(range(len(remaining)), key=lambda i: abs(remaining[i] - note.onset_sec))
        assigned.append(remaining.pop(best_i))
    return assigned


def judge_onset_ok(
    *,
    note_index: int,
    onset_expected: float,
    onset_detected: float | None,
    prev_onset_expected: float | None,
    prev_onset_detected: float | None,
    tempo_bpm: float,
    config: RhythmJudgeConfig,
) -> tuple[bool, float | None]:
    """Return (onset_ok, onset_error_sec). error is detected - expected for the compared quantity."""
    if onset_detected is None:
        return False, None

    tau = config.onset_tolerance_sec(tempo_bpm)
    onset_error = onset_detected - onset_expected

    if note_index == 0 or not config.use_ioi_after_first:
        return abs(onset_error) <= tau, onset_error

    if prev_onset_expected is None or prev_onset_detected is None:
        return abs(onset_error) <= tau, onset_error

    ioi_expected = onset_expected - prev_onset_expected
    ioi_detected = onset_detected - prev_onset_detected
    ioi_error = ioi_detected - ioi_expected
    return abs(ioi_error) <= tau, onset_error


def judge_notes(
    expected_notes: Sequence[ExpectedNote],
    detected_onsets: Sequence[float],
    track: PitchTrack,
    *,
    tempo_bpm: float = 120.0,
    config: RhythmJudgeConfig | None = None,
) -> list[RhythmSegment]:
    """Judge each non-rest note; rests are skipped (no segment)."""
    cfg = config or RhythmJudgeConfig()
    tempo = tempo_bpm if tempo_bpm > 0 else 120.0

    sounding = [n for n in expected_notes if not n.is_rest]
    assigned = _assign_onsets(sounding, detected_onsets)

    segments: list[RhythmSegment] = []
    prev_exp: float | None = None
    prev_det: float | None = None

    for i, note in enumerate(sounding):
        det = assigned[i]
        next_det = assigned[i + 1] if i + 1 < len(assigned) else None
        next_exp = sounding[i + 1].onset_sec if i + 1 < len(sounding) else None

        onset_ok, onset_error = judge_onset_ok(
            note_index=i,
            onset_expected=note.onset_sec,
            onset_detected=det,
            prev_onset_expected=prev_exp,
            prev_onset_detected=prev_det,
            tempo_bpm=tempo,
            config=cfg,
        )

        if cfg.duration_window_mode == "score_grid":
            dur = measure_duration(
                track,
                onset_sec=note.onset_sec,
                next_onset_sec=next_exp,
                duration_expected_sec=note.duration_sec,
                expected_midi=note.pitch_midi,
                tempo_bpm=tempo,
                config=cfg,
            )
        elif cfg.duration_window_mode == "anchored_grid":
            # Standard expected span after start-DTW lock, with pre/post pads so
            # neighbor bleed does not steal the only frames; if user onset is
            # near expected, use it as the closest-frame reference.
            nominal_end = note.onset_sec + note.duration_sec
            if next_exp is not None:
                nominal_end = min(nominal_end, next_exp)
            pre = cfg.grid_pre_sec(tempo)
            post = cfg.grid_post_sec(tempo)
            ref = note.onset_sec
            if det is not None and abs(float(det) - note.onset_sec) <= cfg.onset_tolerance_sec(
                tempo
            ):
                ref = float(det)
            dur = measure_duration(
                track,
                onset_sec=note.onset_sec,
                next_onset_sec=nominal_end,
                duration_expected_sec=note.duration_sec,
                expected_midi=note.pitch_midi,
                tempo_bpm=tempo,
                config=cfg,
                search_pre_sec=pre,
                search_post_sec=post,
                reference_sec=ref,
            )
        elif det is None:
            dur = DurationMeasure(
                duration_detected_sec=0.0,
                duration_expected_sec=note.duration_sec,
                duration_ratio=0.0 if note.duration_sec > 0 else None,
                duration_mode=(
                    "faster_than_quarter"
                    if note.duration_sec < cfg.quarter_sec(tempo)
                    else "quarter_or_longer"
                ),
                valid_frame_count=0,
                duration_ok=False,
            )
        else:
            # Use assigned peak even when onset_ok is False (diagnostic only).
            dur = measure_duration(
                track,
                onset_sec=det,
                next_onset_sec=next_det,
                duration_expected_sec=note.duration_sec,
                expected_midi=note.pitch_midi,
                tempo_bpm=tempo,
                config=cfg,
            )

        # Product rule: only duration failure (or both) counts as wrong.
        # onset-only failure → still rhythm_ok (onset kept as diagnostic via timing_result).
        rhythm_ok = dur.duration_ok
        note_ref = None
        if note.measure is not None or note.note_index_in_measure is not None:
            note_ref = {
                "measure": note.measure,
                "note_index_in_measure": note.note_index_in_measure,
            }

        segments.append(
            RhythmSegment(
                note_ref=note_ref,
                onset_detected_sec=det,
                onset_expected_sec=note.onset_sec,
                onset_error_sec=onset_error,
                onset_ok=onset_ok,
                duration_detected_sec=dur.duration_detected_sec,
                duration_expected_sec=dur.duration_expected_sec,
                duration_ratio=dur.duration_ratio,
                duration_ok=dur.duration_ok,
                duration_mode=dur.duration_mode,
                rhythm_ok=rhythm_ok,
                timing_result=_timing_result(onset_ok, dur.duration_ok),
                valid_frame_count=dur.valid_frame_count,
            )
        )

        prev_exp = note.onset_sec
        prev_det = det

    return segments
