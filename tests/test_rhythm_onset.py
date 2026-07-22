"""Regression C: spectral-flux onset on synthetic PCM."""

from __future__ import annotations

import numpy as np

from music_practice.pitch.config import PitchDetectConfig
from music_practice.rhythm.config import OnsetDetectConfig
from music_practice.rhythm.onset import detect_onsets_audio


def _sine(freq: float, duration: float, sr: int = 22050, amp: float = 0.5) -> np.ndarray:
    n = int(duration * sr)
    t = np.arange(n, dtype=np.float64) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_o_silence():
    sr = 22050
    audio = np.zeros(sr, dtype=np.float32)
    onsets = detect_onsets_audio(audio, sample_rate=sr, tempo=120.0)
    assert len(onsets) == 0


def test_o_two_notes():
    sr = 22050
    # Note at 0.0 and 0.6 with silence gap
    note = _sine(440.0, 0.35, sr=sr)
    gap = np.zeros(int(0.25 * sr), dtype=np.float32)
    audio = np.concatenate([note, gap, note])
    cfg = OnsetDetectConfig.for_tempo(120.0)
    onsets = detect_onsets_audio(audio, sample_rate=sr, config=cfg, tempo=120.0)
    assert len(onsets) >= 2
    # First near 0, second near 0.6
    assert onsets[0] < 0.15
    second = min(onsets[1:], key=lambda t: abs(t - 0.6))
    assert abs(second - 0.6) < 2 * cfg.window_duration_sec + 0.05


def test_o_tempo_frame():
    cfg80 = OnsetDetectConfig.for_tempo(80.0)
    cfg120 = OnsetDetectConfig.for_tempo(120.0)
    assert cfg80.frame_size == PitchDetectConfig.for_tempo(80.0).frame_size == 1024
    assert cfg120.frame_size == 512
    assert cfg80.hop_size == cfg80.frame_size
