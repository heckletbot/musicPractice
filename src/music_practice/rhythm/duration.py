"""Duration measurement from PitchTrack (docs/05 §6.3.4)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from music_practice.pitch.detector import PitchTrack
from music_practice.rhythm.config import RhythmJudgeConfig

DurationMode = Literal["quarter_or_longer", "faster_than_quarter"]


@dataclass
class DurationMeasure:
    duration_detected_sec: float
    duration_expected_sec: float
    duration_ratio: float | None
    duration_mode: DurationMode
    valid_frame_count: int
    duration_ok: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "duration_detected_sec": self.duration_detected_sec,
            "duration_expected_sec": self.duration_expected_sec,
            "duration_ratio": self.duration_ratio,
            "duration_mode": self.duration_mode,
            "valid_frame_count": self.valid_frame_count,
            "duration_ok": self.duration_ok,
        }


def _frames_in_range(track: PitchTrack, t0: float, t1: float) -> list:
    out = []
    for frame in track.frames:
        if t0 <= frame.time_sec < t1:
            out.append(frame)
    return out


def _trim_indices(n: int, trim_ratio: float) -> tuple[int, int]:
    """Return [start, end) after trimming head/tail; each side at least 1 frame when possible."""
    if n <= 0:
        return 0, 0
    if n == 1:
        return 0, 1
    head = max(1, int(n * trim_ratio))
    tail = max(1, int(n * trim_ratio))
    if head + tail >= n:
        # Keep at least one middle frame if possible.
        mid = n // 2
        return mid, mid + 1
    return head, n - tail


def count_valid_pitch_frames(
    track: PitchTrack,
    *,
    t0: float,
    t1: float,
    expected_midi: float,
    pitch_tolerance: float,
    trim: bool,
    trim_ratio: float,
) -> int:
    frames = _frames_in_range(track, t0, t1)
    if not frames:
        return 0
    if trim:
        start, end = _trim_indices(len(frames), trim_ratio)
        frames = frames[start:end]
    count = 0
    for frame in frames:
        if not frame.voiced:
            continue
        if abs(frame.pitch_midi - expected_midi) <= pitch_tolerance:
            count += 1
    return count


def measure_duration(
    track: PitchTrack,
    *,
    onset_sec: float,
    next_onset_sec: float | None,
    duration_expected_sec: float,
    expected_midi: float,
    tempo_bpm: float,
    config: RhythmJudgeConfig | None = None,
    search_pre_sec: float = 0.0,
    search_post_sec: float = 0.0,
    reference_sec: float | None = None,
) -> DurationMeasure:
    """Measure sounding duration relative to expected (quarter-based modes).

    ``onset_sec`` / ``next_onset_sec`` define the nominal note span.
    ``search_pre_sec`` / ``search_post_sec`` expand the pitch search around that
    span (anchored-grid pads). ``reference_sec`` is the time used for
    closest-frame preference (standard expected onset, or user detected onset).
    """
    cfg = config or RhythmJudgeConfig()
    quarter = cfg.quarter_sec(tempo_bpm)
    window = track.window_duration_sec
    ref = float(reference_sec) if reference_sec is not None else float(onset_sec)

    if duration_expected_sec <= 0:
        return DurationMeasure(
            duration_detected_sec=0.0,
            duration_expected_sec=duration_expected_sec,
            duration_ratio=None,
            duration_mode="faster_than_quarter",
            valid_frame_count=0,
            duration_ok=False,
        )

    seg_end = next_onset_sec if next_onset_sec is not None else onset_sec + duration_expected_sec
    if seg_end <= onset_sec:
        seg_end = onset_sec + duration_expected_sec

    faster = duration_expected_sec < quarter
    mode: DurationMode = "faster_than_quarter" if faster else "quarter_or_longer"

    # Fast notes (e.g. 16ths): product rule is ≥1 pitch-matching frame.
    # Do not let an early next-onset (over-detected peak) shrink the search
    # window below the expected duration — otherwise the only frame left may
    # belong to the previous pitch and a valid nearby frame is excluded.
    if faster:
        min_end = onset_sec + max(duration_expected_sec, window)
        if seg_end < min_end:
            seg_end = min_end

    t0 = float(onset_sec) - max(0.0, float(search_pre_sec))
    t1 = float(seg_end) + max(0.0, float(search_post_sec))
    if t1 <= t0:
        t1 = t0 + max(duration_expected_sec, window)

    frames = _frames_in_range(track, t0, t1)
    if faster:
        # ≥1 pitch-matching frame in the window (design for 16ths / fast notes).
        valid = 0
        closest = None
        closest_dist = None
        for frame in frames:
            if not frame.voiced:
                continue
            dist = abs(frame.time_sec - ref)
            if closest_dist is None or dist < closest_dist:
                closest = frame
                closest_dist = dist
            if abs(frame.pitch_midi - expected_midi) <= cfg.duration_pitch_tolerance_semitone:
                valid += 1
        # Prefer the frame closest to the reference (expected or user onset).
        if (
            closest is not None
            and abs(closest.pitch_midi - expected_midi) <= cfg.duration_pitch_tolerance_semitone
        ):
            valid = max(valid, 1)
        detected = valid * window
        ratio = detected / duration_expected_sec if duration_expected_sec > 0 else None
        ok = valid >= 1
    else:
        if not frames:
            valid = 0
            mid_n = 0
        else:
            start, end = _trim_indices(len(frames), cfg.duration_trim_ratio)
            mid = frames[start:end]
            mid_n = len(mid)
            valid = 0
            for frame in mid:
                if not frame.voiced:
                    continue
                if abs(frame.pitch_midi - expected_midi) <= cfg.duration_pitch_tolerance_semitone:
                    valid += 1
        # Extrapolate mid-region pitch density to full expected duration so that
        # a fully correct mid (after attack/release trim) yields ratio ≈ 1.0.
        if mid_n > 0:
            density = valid / mid_n
            detected = density * duration_expected_sec
        else:
            detected = 0.0
        ratio = detected / duration_expected_sec if duration_expected_sec > 0 else None
        if duration_expected_sec >= 2.0 * quarter:
            ok = ratio is not None and ratio >= cfg.duration_half_or_longer_ratio_min
        else:
            ok = ratio is not None and ratio >= cfg.duration_quarter_ratio_min
        if ok and cfg.duration_ratio_max is not None and ratio is not None:
            ok = ratio <= cfg.duration_ratio_max

    return DurationMeasure(
        duration_detected_sec=detected,
        duration_expected_sec=duration_expected_sec,
        duration_ratio=ratio,
        duration_mode=mode,
        valid_frame_count=valid,
        duration_ok=ok,
    )
