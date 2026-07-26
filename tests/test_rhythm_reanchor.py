"""Unit tests for rest re-anchor."""

from __future__ import annotations

from music_practice.pitch.detector import PitchFrame, PitchTrack
from music_practice.rhythm.judge import ExpectedNote
from music_practice.rhythm.reanchor import RestReanchorConfig, apply_rest_reanchors

SR = 22050
FRAME = 512
WINDOW = FRAME / SR


def _fill(t0: float, dur: float, midi: float, *, voiced: bool = True) -> list[PitchFrame]:
    frames = []
    t = t0
    end = t0 + dur
    while t < end - 1e-12:
        frames.append(
            PitchFrame(
                time_sec=t,
                frequency_hz=440.0 if voiced else None,
                pitch_midi=midi if voiced else -1.0,
                pitch="X" if voiced else None,
                voiced=voiced,
            )
        )
        t += WINDOW
    return frames


def test_rest_reanchor_shifts_after_gap():
    # note0 sounds 0-0.45, silence, note1 actually @1.2 (expected 1.0)
    notes = [
        ExpectedNote(onset_sec=0.0, duration_sec=0.5, pitch_midi=60, measure=1),
        ExpectedNote(onset_sec=1.0, duration_sec=0.5, pitch_midi=62, measure=2),
        ExpectedNote(onset_sec=1.5, duration_sec=0.5, pitch_midi=64, measure=2),
    ]
    frames = (
        _fill(0.0, 0.45, 60.0)
        + _fill(0.45, 0.75, 60.0, voiced=False)
        + _fill(1.2, 0.5, 62.0)
        + _fill(1.7, 0.5, 64.0)
    )
    track = PitchTrack(
        sample_rate=SR, frame_size=FRAME, window_duration_sec=WINDOW, frames=frames
    )
    out, events = apply_rest_reanchors(
        notes,
        track,
        tempo_bpm=120.0,
        config=RestReanchorConfig(enabled=True, min_rest_beat=0.5, min_voiced_frames=3),
    )
    assert len(events) == 1
    assert events[0].rest_start_sec < 0.7
    assert abs(events[0].shift_sec - 0.2) < 0.08
    assert abs(out[1].onset_sec - 1.2) < 0.08
    assert abs(out[2].onset_sec - 1.7) < 0.08
    assert abs(out[0].onset_sec - 0.0) < 1e-9


def test_rest_reanchor_calibrates_prev_note_end():
    notes = [
        ExpectedNote(onset_sec=0.0, duration_sec=0.5, pitch_midi=60, measure=1),
        ExpectedNote(onset_sec=1.0, duration_sec=0.5, pitch_midi=62, measure=2),
    ]
    # Previous note actually ends early (~0.3), rest, next at 1.0
    frames = (
        _fill(0.0, 0.30, 60.0)
        + _fill(0.30, 0.70, 60.0, voiced=False)
        + _fill(1.0, 0.5, 62.0)
    )
    track = PitchTrack(
        sample_rate=SR, frame_size=FRAME, window_duration_sec=WINDOW, frames=frames
    )
    out, events = apply_rest_reanchors(
        notes,
        track,
        tempo_bpm=120.0,
        config=RestReanchorConfig(enabled=True, min_rest_beat=0.5, min_voiced_frames=3),
    )
    assert len(events) == 1
    assert events[0].prev_note_end_detected_sec < 0.45
    assert events[0].rest_start_sec == events[0].prev_note_end_detected_sec
    # next onset already near expected → small/zero shift ok
    assert abs(out[1].onset_sec - 1.0) < 0.08


def test_rest_reanchor_disabled_noop():
    notes = [
        ExpectedNote(onset_sec=0.0, duration_sec=0.5, pitch_midi=60),
        ExpectedNote(onset_sec=1.0, duration_sec=0.5, pitch_midi=62),
    ]
    track = PitchTrack(
        sample_rate=SR, frame_size=FRAME, window_duration_sec=WINDOW, frames=[]
    )
    out, events = apply_rest_reanchors(
        notes,
        track,
        tempo_bpm=120.0,
        config=RestReanchorConfig(enabled=False),
    )
    assert events == []
    assert out[1].onset_sec == 1.0
