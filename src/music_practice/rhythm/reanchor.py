"""Re-lock expected timeline after score rests (note-end + next-onset)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from music_practice.pitch.detector import PitchTrack
from music_practice.rhythm.judge import ExpectedNote


@dataclass(frozen=True)
class RestReanchorConfig:
    """When a sounding note is followed by a rest gap, calibrate twice:
    1) previous note end (= rest start), 2) next note onset.
    """

    enabled: bool = True
    # Trigger when score silence between note-end and next onset is ≥ this many beats.
    min_rest_beat: float = 0.5
    # How far past the expected previous note-end to search for the real release.
    note_end_search_post_beat: float = 1.0
    # How far before expected previous note-end to allow an early release.
    note_end_search_pre_beat: float = 0.5
    # After rest starts, search for next onset within [rest_start + min_rest*scale, expected+post].
    search_post_beat: float = 2.5
    # Also allow searching a little before expected next onset (but never before rest_start).
    search_pre_beat: float = 0.5
    pitch_tolerance_semitone: float = 1.0
    min_voiced_frames: int = 4
    run_gap_sec: float = 0.08
    # Require this much unvoiced/non-matching time to confirm rest has started.
    rest_confirm_sec: float = 0.06
    max_shift_beat: float = 2.5


@dataclass(frozen=True)
class RestReanchorEvent:
    note_index: int  # 0-based index of the NEW note after the rest
    measure: int | None
    note_index_in_measure: int | None
    pitch_midi: float
    rest_gap_sec: float
    prev_note_end_expected_sec: float
    prev_note_end_detected_sec: float
    rest_start_sec: float
    expected_sec_before: float
    detected_sec: float
    shift_sec: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "note_index": self.note_index,
            "measure": self.measure,
            "note_index_in_measure": self.note_index_in_measure,
            "pitch_midi": self.pitch_midi,
            "rest_gap_sec": round(self.rest_gap_sec, 4),
            "prev_note_end_expected_sec": round(self.prev_note_end_expected_sec, 4),
            "prev_note_end_detected_sec": round(self.prev_note_end_detected_sec, 4),
            "rest_start_sec": round(self.rest_start_sec, 4),
            "expected_sec_before": round(self.expected_sec_before, 4),
            "detected_sec": round(self.detected_sec, 4),
            "shift_sec": round(self.shift_sec, 4),
        }


def _beat_sec(tempo_bpm: float) -> float:
    return 60.0 / tempo_bpm if tempo_bpm > 0 else 0.5


def _matching_voiced_times(
    track: PitchTrack,
    *,
    target_midi: float,
    search_lo: float,
    search_hi: float,
    pitch_tol: float,
) -> list[float]:
    out: list[float] = []
    for f in track.frames:
        if f.time_sec < search_lo:
            continue
        if f.time_sec >= search_hi:
            break
        if not f.voiced:
            continue
        if abs(float(f.pitch_midi) - float(target_midi)) <= pitch_tol:
            out.append(float(f.time_sec))
    return out


def _find_note_end(
    track: PitchTrack,
    *,
    target_midi: float,
    onset_sec: float,
    expected_end_sec: float,
    search_pre_sec: float,
    search_post_sec: float,
    hard_hi_sec: float,
    pitch_tol: float,
    rest_confirm_sec: float,
    hop_hint_sec: float,
) -> float | None:
    """Release time of previous note; never later than ``hard_hi_sec`` (next onset)."""
    lo = max(onset_sec, expected_end_sec - search_pre_sec)
    hi = min(expected_end_sec + search_post_sec, hard_hi_sec)
    if hi <= lo:
        return None
    times = _matching_voiced_times(
        track,
        target_midi=target_midi,
        search_lo=lo,
        search_hi=hi,
        pitch_tol=pitch_tol,
    )
    if not times:
        return None

    confirm = max(rest_confirm_sec, hop_hint_sec * 2)
    # Prefer the matching frame closest to expected_end that is followed by silence/other.
    ranked = sorted(times, key=lambda t: abs(t - expected_end_sec))
    for t in ranked:
        saw_other = False
        for f in track.frames:
            if f.time_sec <= t + 1e-9:
                continue
            if f.time_sec > t + confirm:
                break
            if not f.voiced or abs(float(f.pitch_midi) - float(target_midi)) > pitch_tol:
                saw_other = True
                break
        if saw_other:
            end = float(t) + max(hop_hint_sec, 0.0)
            return min(end, hard_hi_sec)

    end = float(times[-1]) + max(hop_hint_sec, 0.0)
    return min(end, hard_hi_sec)


def _find_pitch_onset(
    track: PitchTrack,
    *,
    target_midi: float,
    search_lo: float,
    search_hi: float,
    expected_sec: float,
    pitch_tol: float,
    min_frames: int,
    run_gap_sec: float,
) -> float | None:
    """Matching-pitch run start in window closest to ``expected_sec``."""
    frames = [
        f
        for f in track.frames
        if search_lo <= f.time_sec < search_hi
        and f.voiced
        and abs(float(f.pitch_midi) - float(target_midi)) <= pitch_tol
    ]
    if len(frames) < min_frames:
        return None

    runs: list[list] = []
    cur: list = []
    for f in frames:
        if not cur or f.time_sec - cur[-1].time_sec <= run_gap_sec:
            cur.append(f)
        else:
            runs.append(cur)
            cur = [f]
    if cur:
        runs.append(cur)

    candidates = [float(run[0].time_sec) for run in runs if len(run) >= min_frames]
    if not candidates:
        return None
    return min(candidates, key=lambda t: abs(t - expected_sec))


def apply_rest_reanchors(
    expected_notes: Sequence[ExpectedNote],
    track: PitchTrack,
    *,
    tempo_bpm: float,
    config: RestReanchorConfig | None = None,
) -> tuple[list[ExpectedNote], list[RestReanchorEvent]]:
    """
    After a score rest gap:

    1. Calibrate previous note end from pitch release.
    2. Treat that as rest start.
    3. Calibrate next note onset after rest start; shift all later expected onsets.
    """
    cfg = config or RestReanchorConfig()
    notes = [
        ExpectedNote(
            onset_sec=float(n.onset_sec),
            duration_sec=float(n.duration_sec),
            pitch_midi=float(n.pitch_midi),
            measure=n.measure,
            note_index_in_measure=n.note_index_in_measure,
            is_rest=bool(n.is_rest),
        )
        for n in expected_notes
    ]
    if not cfg.enabled or len(notes) < 2:
        return notes, []

    beat = _beat_sec(tempo_bpm)
    min_gap = cfg.min_rest_beat * beat
    end_pre = cfg.note_end_search_pre_beat * beat
    end_post = cfg.note_end_search_post_beat * beat
    search_pre = cfg.search_pre_beat * beat
    search_post = cfg.search_post_beat * beat
    max_shift = cfg.max_shift_beat * beat
    hop = float(getattr(track, "window_duration_sec", 0.02) or 0.02)

    events: list[RestReanchorEvent] = []
    for i in range(1, len(notes)):
        if notes[i].is_rest or notes[i - 1].is_rest:
            continue
        prev = notes[i - 1]
        prev_end_expected = prev.onset_sec + max(0.0, prev.duration_sec)
        gap = notes[i].onset_sec - prev_end_expected
        if gap + 1e-9 < min_gap:
            continue

        expected = float(notes[i].onset_sec)

        # --- 1) calibrate previous note end (must finish before next expected onset) ---
        prev_end_det = _find_note_end(
            track,
            target_midi=float(prev.pitch_midi),
            onset_sec=float(prev.onset_sec),
            expected_end_sec=float(prev_end_expected),
            search_pre_sec=end_pre,
            search_post_sec=end_post,
            hard_hi_sec=float(expected) - cfg.rest_confirm_sec,
            pitch_tol=cfg.pitch_tolerance_semitone,
            rest_confirm_sec=cfg.rest_confirm_sec,
            hop_hint_sec=hop,
        )
        if prev_end_det is None:
            prev_end_det = float(prev_end_expected)

        # Guard: rest cannot start after/at the next note's expected time.
        if prev_end_det >= expected - 1e-6:
            prev_end_det = float(prev_end_expected)

        rest_start = float(prev_end_det)

        new_dur = max(hop, rest_start - float(prev.onset_sec))
        if abs(new_dur - prev.duration_sec) <= max_shift:
            prev.duration_sec = new_dur

        # --- 2) after rest starts, calibrate next note onset ---
        search_lo = max(rest_start + cfg.rest_confirm_sec, expected - search_pre)
        search_hi = expected + search_post
        if search_hi <= search_lo:
            search_hi = search_lo + search_post

        detected = _find_pitch_onset(
            track,
            target_midi=float(notes[i].pitch_midi),
            search_lo=search_lo,
            search_hi=search_hi,
            expected_sec=expected,
            pitch_tol=cfg.pitch_tolerance_semitone,
            min_frames=cfg.min_voiced_frames,
            run_gap_sec=cfg.run_gap_sec,
        )
        if detected is None:
            continue

        shift = detected - expected
        if abs(shift) > max_shift:
            continue

        if abs(shift) >= 1e-4:
            for j in range(i, len(notes)):
                notes[j].onset_sec = float(notes[j].onset_sec) + shift

        events.append(
            RestReanchorEvent(
                note_index=i,
                measure=notes[i].measure,
                note_index_in_measure=notes[i].note_index_in_measure,
                pitch_midi=float(notes[i].pitch_midi),
                rest_gap_sec=float(gap),
                prev_note_end_expected_sec=float(prev_end_expected),
                prev_note_end_detected_sec=float(prev_end_det),
                rest_start_sec=float(rest_start),
                expected_sec_before=expected,
                detected_sec=float(detected),
                shift_sec=float(shift),
            )
        )

    return notes, events
