"""Regression A: pure rhythm judgement (docs/05 §6.3), no WAV."""

from __future__ import annotations

import pytest

from music_practice.pitch.detector import PitchFrame, PitchTrack
from music_practice.rhythm.config import RhythmJudgeConfig
from music_practice.rhythm.judge import ExpectedNote, judge_notes


SR = 22050
FRAME = 512
WINDOW = FRAME / SR  # ~0.02322


def _track_constant(
    *,
    t0: float,
    duration: float,
    midi: float,
    window: float = WINDOW,
    flash_head_midi: float | None = None,
    flash_tail_midi: float | None = None,
) -> PitchTrack:
    """Build voiced frames covering [t0, t0+duration)."""
    frames: list[PitchFrame] = []
    t = 0.0
    end = t0 + duration
    # Cover from 0 so indexing by time works for multi-note.
    while t < end + window:
        in_seg = t0 <= t < end
        if not in_seg:
            frames.append(
                PitchFrame(time_sec=t, frequency_hz=None, pitch_midi=-1.0, pitch=None, voiced=False)
            )
        else:
            rel = (t - t0) / duration if duration > 0 else 0.0
            m = midi
            if flash_head_midi is not None and rel < 0.1:
                m = flash_head_midi
            if flash_tail_midi is not None and rel > 0.9:
                m = flash_tail_midi
            frames.append(
                PitchFrame(
                    time_sec=t,
                    frequency_hz=440.0,
                    pitch_midi=m,
                    pitch="A4",
                    voiced=True,
                )
            )
        t += window
    return PitchTrack(
        sample_rate=SR,
        frame_size=FRAME,
        window_duration_sec=window,
        frames=frames,
    )


def test_j_onset_first_within_tolerance():
    cfg = RhythmJudgeConfig()
    tau = cfg.onset_tolerance_sec(120.0)  # 0.175
    notes = [ExpectedNote(onset_sec=0.0, duration_sec=0.5, pitch_midi=69)]
    track = _track_constant(t0=0.05, duration=0.5, midi=69)
    segs = judge_notes(notes, [0.05], track, tempo_bpm=120.0, config=cfg)
    assert segs[0].onset_ok is True
    assert abs(segs[0].onset_error_sec - 0.05) < 1e-9

    segs_bad = judge_notes(notes, [tau + 0.05], track, tempo_bpm=120.0, config=cfg)
    assert segs_bad[0].onset_ok is False


def test_j_onset_ioi_survives_global_lag():
    """Whole phrase late but IOI correct → subsequent notes onset_ok."""
    cfg = RhythmJudgeConfig(use_ioi_after_first=True)
    notes = [
        ExpectedNote(onset_sec=0.0, duration_sec=0.5, pitch_midi=69),
        ExpectedNote(onset_sec=0.5, duration_sec=0.5, pitch_midi=71),
    ]
    lag = 0.3  # > tau @120, first fails absolute onset
    detected = [0.0 + lag, 0.5 + lag]
    track = _track_constant(t0=lag, duration=1.0, midi=69)
    # Extend track for second note pitch
    track2 = _track_constant(t0=lag, duration=0.5, midi=69)
    frames = list(track2.frames)
    for fr in _track_constant(t0=lag + 0.5, duration=0.5, midi=71).frames:
        if fr.time_sec >= lag + 0.5:
            frames.append(fr)
    # Merge properly
    merged = {}
    for fr in _track_constant(t0=lag, duration=0.5, midi=69).frames:
        merged[round(fr.time_sec, 6)] = fr
    for fr in _track_constant(t0=lag + 0.5, duration=0.5, midi=71).frames:
        if fr.voiced:
            merged[round(fr.time_sec, 6)] = fr
    track = PitchTrack(
        sample_rate=SR,
        frame_size=FRAME,
        window_duration_sec=WINDOW,
        frames=[merged[k] for k in sorted(merged)],
    )
    segs = judge_notes(notes, detected, track, tempo_bpm=120.0, config=cfg)
    assert segs[0].onset_ok is False  # absolute lag
    assert segs[1].onset_ok is True  # IOI ok


def test_j_onset_cap_slow_tempo():
    cfg = RhythmJudgeConfig()
    # At 40 BPM, 0.35 * beat = 0.35 * 1.5 = 0.525 → capped at 0.25
    assert cfg.onset_tolerance_sec(40.0) == pytest.approx(0.25)


def test_j_onset_tau_scales_152():
    cfg = RhythmJudgeConfig()
    beat = 60.0 / 152.0
    assert cfg.onset_tolerance_sec(152.0) == pytest.approx(min(0.35 * beat, 0.25))


def _ratio_track(onset: float, duration_exp: float, density: float, midi: float = 69.0) -> PitchTrack:
    """Fill [onset, onset+duration); after trim, mid has given correct-pitch density.

    Implementation extrapolates mid density → duration_ratio ≈ density.
    """
    cfg = RhythmJudgeConfig()
    seg_frames_n = max(1, int(round(duration_exp / WINDOW)))
    frames: list[PitchFrame] = []
    seg = []
    for i in range(seg_frames_n):
        seg.append(
            PitchFrame(
                time_sec=onset + i * WINDOW,
                frequency_hz=440.0,
                pitch_midi=midi,
                pitch="A4",
                voiced=True,
            )
        )
    from music_practice.rhythm.duration import _trim_indices

    start, end = _trim_indices(len(seg), cfg.duration_trim_ratio)
    mid = list(seg[start:end])
    target_ok = int(round(density * len(mid))) if mid else 0
    for j, fr in enumerate(mid):
        if j >= target_ok:
            mid[j] = PitchFrame(
                time_sec=fr.time_sec,
                frequency_hz=440.0,
                pitch_midi=midi + 5,
                pitch="D5",
                voiced=True,
            )
    rebuilt = seg[:start] + mid + seg[end:]
    t = 0.0
    while t < onset - 1e-9:
        frames.append(
            PitchFrame(time_sec=t, frequency_hz=None, pitch_midi=-1.0, pitch=None, voiced=False)
        )
        t += WINDOW
    frames.extend(rebuilt)
    return PitchTrack(
        sample_rate=SR, frame_size=FRAME, window_duration_sec=WINDOW, frames=frames
    )


@pytest.mark.parametrize("density,ok", [(0.79, False), (0.80, True)])
def test_j_dur_half(density, ok):
    """≥ 2× quarter (1.0s @120) needs mid density / ratio ≥ 0.8."""
    cfg = RhythmJudgeConfig()
    notes = [ExpectedNote(onset_sec=0.0, duration_sec=1.0, pitch_midi=69)]
    track = _ratio_track(0.0, 1.0, density)
    segs = judge_notes(notes, [0.0], track, tempo_bpm=120.0, config=cfg)
    assert segs[0].duration_mode == "quarter_or_longer"
    assert segs[0].duration_ok is ok


@pytest.mark.parametrize("density,ok", [(0.40, False), (0.60, True)])
def test_j_dur_quarter(density, ok):
    """Quarter note needs mid density / ratio ≥ 0.5."""
    cfg = RhythmJudgeConfig()
    notes = [ExpectedNote(onset_sec=0.0, duration_sec=0.5, pitch_midi=69)]
    track = _ratio_track(0.0, 0.5, density)
    segs = judge_notes(notes, [0.0], track, tempo_bpm=120.0, config=cfg)
    assert segs[0].duration_ok is ok

def test_j_dur_fast():
    cfg = RhythmJudgeConfig()
    notes = [ExpectedNote(onset_sec=0.0, duration_sec=0.25, pitch_midi=69)]  # eighth
    # 0 frames
    empty = PitchTrack(sample_rate=SR, frame_size=FRAME, window_duration_sec=WINDOW, frames=[])
    segs = judge_notes(notes, [0.0], empty, tempo_bpm=120.0, config=cfg)
    assert segs[0].duration_mode == "faster_than_quarter"
    assert segs[0].duration_ok is False

    # 1 valid frame
    track = PitchTrack(
        sample_rate=SR,
        frame_size=FRAME,
        window_duration_sec=WINDOW,
        frames=[
            PitchFrame(
                time_sec=0.0, frequency_hz=440.0, pitch_midi=69.0, pitch="A4", voiced=True
            )
        ],
    )
    segs = judge_notes(notes, [0.0], track, tempo_bpm=120.0, config=cfg)
    assert segs[0].duration_ok is True


def test_j_trim_flash():
    """Head/tail neighbor flash should still pass for half note if mid is long enough."""
    cfg = RhythmJudgeConfig()
    notes = [ExpectedNote(onset_sec=0.0, duration_sec=1.0, pitch_midi=69)]
    track = _track_constant(
        t0=0.0, duration=1.0, midi=69.0, flash_head_midi=72.0, flash_tail_midi=65.0
    )
    segs = judge_notes(notes, [0.0], track, tempo_bpm=120.0, config=cfg)
    assert segs[0].duration_ok is True


def test_j_boundary_no_onset():
    """No detected peak → onset and duration both fail."""
    notes = [ExpectedNote(onset_sec=0.0, duration_sec=0.5, pitch_midi=69)]
    track = _track_constant(t0=0.0, duration=0.5, midi=69)
    segs = judge_notes(notes, [], track, tempo_bpm=120.0)
    assert segs[0].onset_ok is False
    assert segs[0].duration_ok is False
    assert segs[0].rhythm_ok is False
    assert segs[0].timing_result == "BOTH_ERROR"


def test_j_boundary_onset_no_pitch():
    notes = [ExpectedNote(onset_sec=0.0, duration_sec=0.5, pitch_midi=69)]
    empty = PitchTrack(sample_rate=SR, frame_size=FRAME, window_duration_sec=WINDOW, frames=[])
    segs = judge_notes(notes, [0.0], empty, tempo_bpm=120.0)
    assert segs[0].onset_ok is True
    assert segs[0].duration_ok is False
    assert segs[0].timing_result == "DURATION_ERROR"


def test_j_timing_onset_only():
    """Late detected onset fails onset_ok, but duration still uses that peak."""
    cfg = RhythmJudgeConfig()
    notes = [ExpectedNote(onset_sec=0.0, duration_sec=0.5, pitch_midi=69)]
    track = _track_constant(t0=0.4, duration=0.5, midi=69)
    segs = judge_notes(notes, [0.4], track, tempo_bpm=120.0, config=cfg)
    assert segs[0].onset_ok is False
    assert segs[0].duration_ok is True
    assert segs[0].rhythm_ok is True
    assert segs[0].timing_result == "ONSET_ERROR"


def test_j_rest_skipped():
    notes = [
        ExpectedNote(onset_sec=0.0, duration_sec=0.5, pitch_midi=69, is_rest=True),
        ExpectedNote(onset_sec=0.5, duration_sec=0.5, pitch_midi=71),
    ]
    track = _track_constant(t0=0.5, duration=0.5, midi=71)
    segs = judge_notes(notes, [0.5], track, tempo_bpm=120.0)
    assert len(segs) == 1
    assert segs[0].onset_expected_sec == 0.5


def test_j_score_grid_ignores_detected_onset_for_duration():
    """score_grid measures duration on expected timeline even if detected onset is wrong/missing."""
    cfg = RhythmJudgeConfig(duration_window_mode="score_grid")
    notes = [
        ExpectedNote(onset_sec=0.0, duration_sec=0.5, pitch_midi=69),
        ExpectedNote(onset_sec=0.5, duration_sec=0.5, pitch_midi=71),
    ]
    # Pitch sits on the score grid; detected onsets are badly shifted / incomplete.
    merged = {}
    for fr in _track_constant(t0=0.0, duration=0.5, midi=69).frames:
        merged[round(fr.time_sec, 6)] = fr
    for fr in _track_constant(t0=0.5, duration=0.5, midi=71).frames:
        if fr.voiced:
            merged[round(fr.time_sec, 6)] = fr
    track = PitchTrack(
        sample_rate=SR,
        frame_size=FRAME,
        window_duration_sec=WINDOW,
        frames=[merged[k] for k in sorted(merged)],
    )
    segs = judge_notes(notes, [0.35], track, tempo_bpm=120.0, config=cfg)
    assert segs[0].duration_ok is True
    assert segs[1].duration_ok is True
    assert segs[0].rhythm_ok is True
    assert segs[1].rhythm_ok is True
    # Missing second detected onset → onset diagnostic fails, but duration still ok.
    assert segs[1].onset_ok is False


def test_j_anchored_grid_uses_pre_post_pads():
    """anchored_grid keeps standard expected times but searches pre/post pads."""
    cfg = RhythmJudgeConfig(
        duration_window_mode="anchored_grid",
        grid_pre_beat=0.25,
        grid_post_beat=0.25,
    )
    # 16th @120 = 0.125s; pitch for note0 only appears slightly before expected onset.
    notes = [
        ExpectedNote(onset_sec=0.1, duration_sec=0.125, pitch_midi=69),
        ExpectedNote(onset_sec=0.225, duration_sec=0.125, pitch_midi=71),
    ]
    frames = []
    t = 0.0
    while t < 0.4:
        # Target pitch for note0 lives in the pre-pad (0.05), not after 0.1 only.
        if 0.05 <= t < 0.2:
            midi, name = 69.0, "A4"
            voiced = True
        elif 0.2 <= t < 0.35:
            midi, name = 71.0, "B4"
            voiced = True
        else:
            midi, name, voiced = -1.0, None, False
        frames.append(
            PitchFrame(
                time_sec=t,
                frequency_hz=440.0 if voiced else None,
                pitch_midi=midi,
                pitch=name,
                voiced=voiced,
            )
        )
        t += WINDOW
    track = PitchTrack(
        sample_rate=SR, frame_size=FRAME, window_duration_sec=WINDOW, frames=frames
    )
    # Detected onset slightly late but within tolerance — used as reference.
    segs = judge_notes(notes, [0.12, 0.24], track, tempo_bpm=120.0, config=cfg)
    assert segs[0].duration_ok is True
    assert segs[1].duration_ok is True
