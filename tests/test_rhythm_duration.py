"""Regression B: duration measurement from synthetic PitchTrack."""

from __future__ import annotations

from music_practice.pitch.detector import PitchFrame, PitchTrack
from music_practice.rhythm.config import RhythmJudgeConfig
from music_practice.rhythm.duration import _trim_indices, measure_duration

SR = 22050
FRAME = 512
WINDOW = FRAME / SR


def _track(frames: list[PitchFrame]) -> PitchTrack:
    return PitchTrack(
        sample_rate=SR, frame_size=FRAME, window_duration_sec=WINDOW, frames=frames
    )


def test_trim_indices_minimum_one():
    assert _trim_indices(10, 0.15) == (1, 9) or _trim_indices(10, 0.15)[0] >= 1
    start, end = _trim_indices(20, 0.15)
    assert start == max(1, int(20 * 0.15))
    assert end == 20 - max(1, int(20 * 0.15))


def test_measure_counts_only_within_tolerance():
    frames = [
        PitchFrame(time_sec=i * WINDOW, frequency_hz=440.0, pitch_midi=69.0, pitch="A4", voiced=True)
        for i in range(30)
    ]
    # Corrupt some mid frames beyond ±1
    for i in range(10, 15):
        frames[i] = PitchFrame(
            time_sec=frames[i].time_sec,
            frequency_hz=500.0,
            pitch_midi=72.0,
            pitch="C5",
            voiced=True,
        )
    track = _track(frames)
    m = measure_duration(
        track,
        onset_sec=0.0,
        next_onset_sec=30 * WINDOW,
        duration_expected_sec=30 * WINDOW,
        expected_midi=69.0,
        tempo_bpm=120.0,
    )
    assert m.duration_mode == "quarter_or_longer"
    assert m.valid_frame_count < 30
    assert 0.0 < (m.duration_ratio or 0) < 1.0


def test_fast_mode_one_frame():
    track = _track(
        [
            PitchFrame(
                time_sec=0.0, frequency_hz=440.0, pitch_midi=69.5, pitch="A4", voiced=True
            )
        ]
    )
    m = measure_duration(
        track,
        onset_sec=0.0,
        next_onset_sec=0.25,
        duration_expected_sec=0.25,
        expected_midi=69.0,
        tempo_bpm=120.0,
    )
    assert m.duration_mode == "faster_than_quarter"
    assert m.duration_ok is True
    assert m.valid_frame_count == 1


def test_fast_mode_ignores_too_early_next_onset():
    """16th-note window must not shrink to one bleed frame when next peak is ~1 frame away."""
    # onset at 0; next onset at 1 frame; correct pitch appears at 2nd frame (still within 16th).
    frames = [
        PitchFrame(time_sec=0.0, frequency_hz=400.0, pitch_midi=70.0, pitch="A#4", voiced=True),
        PitchFrame(time_sec=WINDOW, frequency_hz=440.0, pitch_midi=69.0, pitch="A4", voiced=True),
        PitchFrame(time_sec=2 * WINDOW, frequency_hz=440.0, pitch_midi=69.0, pitch="A4", voiced=True),
    ]
    track = _track(frames)
    m = measure_duration(
        track,
        onset_sec=0.0,
        next_onset_sec=WINDOW,  # over-detected: collapses window to first frame only
        duration_expected_sec=0.129,  # ~16th @116
        expected_midi=69.0,
        tempo_bpm=60.0,
    )
    assert m.duration_mode == "faster_than_quarter"
    assert m.duration_ok is True
    assert m.valid_frame_count >= 1


def test_duration_mode_quarter_boundary():
    cfg = RhythmJudgeConfig()
    # Exactly one quarter @120
    frames = [
        PitchFrame(time_sec=i * WINDOW, frequency_hz=440.0, pitch_midi=69.0, pitch="A4", voiced=True)
        for i in range(int(0.5 / WINDOW) + 2)
    ]
    m = measure_duration(
        _track(frames),
        onset_sec=0.0,
        next_onset_sec=0.5,
        duration_expected_sec=0.5,
        expected_midi=69.0,
        tempo_bpm=120.0,
        config=cfg,
    )
    assert m.duration_mode == "quarter_or_longer"
    assert (m.duration_ratio or 0) >= 0.5
    assert m.duration_ok is True
