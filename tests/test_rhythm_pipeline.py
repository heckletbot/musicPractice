"""Regression D: pipeline smoke (quarter + eighth)."""

from __future__ import annotations

from music_practice.pitch.detector import PitchFrame, PitchTrack
from music_practice.rhythm.judge import ExpectedNote
from music_practice.rhythm.pipeline import evaluate_rhythm_from_track
from music_practice.utils.observe import to_observable_dict

SR = 22050
FRAME = 512
WINDOW = FRAME / SR


def _fill(t0: float, dur: float, midi: float) -> list[PitchFrame]:
    frames = []
    t = t0
    end = t0 + dur
    while t < end - 1e-12:
        frames.append(
            PitchFrame(
                time_sec=t, frequency_hz=440.0, pitch_midi=midi, pitch="A4", voiced=True
            )
        )
        t += WINDOW
    return frames


def test_pipeline_quarter_plus_eighth():
    notes = [
        ExpectedNote(onset_sec=0.0, duration_sec=0.5, pitch_midi=69, measure=1, note_index_in_measure=0),
        ExpectedNote(onset_sec=0.5, duration_sec=0.25, pitch_midi=71, measure=1, note_index_in_measure=1),
    ]
    frames = _fill(0.0, 0.5, 69.0) + _fill(0.5, 0.25, 71.0)
    track = PitchTrack(
        sample_rate=SR, frame_size=FRAME, window_duration_sec=WINDOW, frames=frames
    )
    segs = evaluate_rhythm_from_track(notes, [0.0, 0.5], track, tempo_bpm=120.0)
    assert len(segs) == 2
    assert segs[0].rhythm_ok is True
    assert segs[0].duration_mode == "quarter_or_longer"
    assert segs[1].rhythm_ok is True
    assert segs[1].duration_mode == "faster_than_quarter"
    payload = [to_observable_dict(s.to_dict()) for s in segs]
    assert payload[0]["timing_result"] == "CORRECT"
    assert "onset_ok" in payload[0]
