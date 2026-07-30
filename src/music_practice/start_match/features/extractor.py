"""Audio loading and Mel feature extraction."""

from __future__ import annotations

from pathlib import Path

import librosa
import numpy as np

from music_practice.start_match.types import FeatureConfig


def load_audio_mono(path: Path, target_sr: int | None) -> tuple[np.ndarray, int]:
    audio, sample_rate = librosa.load(path, sr=target_sr, mono=True)
    return audio.astype(np.float32), int(sample_rate)


def compute_mel_db(
    audio: np.ndarray,
    sample_rate: int,
    config: FeatureConfig,
) -> np.ndarray:
    fmax = config.fmax if config.fmax is not None else float(sample_rate) / 2.0
    mel_power = librosa.feature.melspectrogram(
        y=audio,
        sr=sample_rate,
        n_fft=config.n_fft,
        hop_length=config.hop_length,
        win_length=config.win_length,
        n_mels=config.n_mels,
        fmin=config.fmin,
        fmax=fmax,
        power=2.0,
    )
    if config.power_to_db_ref == "fixed":
        mel_db = librosa.power_to_db(mel_power, ref=1.0)
    else:
        mel_db = librosa.power_to_db(mel_power, ref=np.max)
    return mel_db.T.astype(np.float32)


def normalize_minmax(values: np.ndarray) -> np.ndarray:
    min_value = float(values.min())
    max_value = float(values.max())
    if max_value == min_value:
        return np.zeros_like(values, dtype=np.float32)
    return ((values - min_value) / (max_value - min_value)).astype(np.float32)


def compute_mel_frames(audio: np.ndarray, sample_rate: int, config: FeatureConfig) -> np.ndarray:
    """Return mel frames [T, D]."""
    mel_db = compute_mel_db(audio, sample_rate, config)
    if config.normalize_minmax:
        return normalize_minmax(mel_db)
    return mel_db


def standardize_with_template_stats(
    template_mel: np.ndarray,
    query_mel: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    mean = template_mel.mean(axis=0, keepdims=True)
    std = template_mel.std(axis=0, keepdims=True)
    std = np.where(std < 1e-6, 1.0, std)
    return (template_mel - mean) / std, (query_mel - mean) / std


def wav_to_mel(path: Path, config: FeatureConfig) -> tuple[np.ndarray, float, int]:
    audio, sr = load_audio_mono(path, config.sample_rate)
    duration_sec = len(audio) / sr
    mel = compute_mel_frames(audio, sr, config)
    return mel, duration_sec, sr
