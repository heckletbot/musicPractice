"""Pitch-oriented feature extraction (Chroma-CQT + CENS + delta + context)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np

from music_practice.start_match.features.preprocess import PreprocessConfig, apply_preprocess, load_and_preprocess_for_pitch, pitch_preprocess_config
from music_practice.start_match.types import PitchFeatureConfig


@dataclass
class PitchSequence:
    features: np.ndarray
    center_frames: np.ndarray
    sample_rate: int
    hop_length: int
    duration_sec: float

    @property
    def num_frames(self) -> int:
        return int(self.features.shape[0])


def extract_chroma_cqt(
    audio: np.ndarray,
    sample_rate: int,
    config: PitchFeatureConfig,
) -> np.ndarray:
    """Return chroma [T, n_chroma]; long audio is processed in chunks."""
    chunk_samples = int(60 * sample_rate)
    if len(audio) <= chunk_samples:
        return _extract_chroma_single(audio, sample_rate, config)
    hop = config.hop_length
    overlap = max(hop, int(2 * sample_rate))  # 2s overlap
    chunks: list[np.ndarray] = []
    start = 0
    while start < len(audio):
        end = min(len(audio), start + chunk_samples)
        piece = audio[start:end]
        feat = _extract_chroma_single(piece, sample_rate, config)
        if chunks:
            skip = int(round(overlap / hop))
            feat = feat[skip:]
        chunks.append(feat)
        if end >= len(audio):
            break
        start = end - overlap
    if not chunks:
        return _extract_chroma_single(audio, sample_rate, config)
    return np.concatenate(chunks, axis=0).astype(np.float32)


def _extract_chroma_single(
    audio: np.ndarray,
    sample_rate: int,
    config: PitchFeatureConfig,
) -> np.ndarray:
    long_threshold = int(180 * sample_rate)
    if len(audio) > long_threshold or len(audio) > int(60 * sample_rate):
        chroma = librosa.feature.chroma_stft(
            y=audio,
            sr=sample_rate,
            hop_length=config.hop_length,
            n_fft=1024,
            n_chroma=config.n_chroma,
        )
        return chroma.T.astype(np.float32)
    chroma = librosa.feature.chroma_cqt(
        y=audio,
        sr=sample_rate,
        hop_length=config.hop_length,
        n_chroma=config.n_chroma,
    )
    return chroma.T.astype(np.float32)


def smooth_chroma(features: np.ndarray, win: int) -> np.ndarray:
    """Temporal mean smoothing along time axis."""
    if win <= 1 or features.shape[0] == 0:
        return features.astype(np.float32)
    kernel = np.ones(win, dtype=np.float32) / win
    smoothed = np.vstack([np.convolve(row, kernel, mode="same") for row in features.T])
    return smoothed.T.astype(np.float32)


def l2_normalize_frames(features: np.ndarray) -> np.ndarray:
    """L2-normalize each frame."""
    norm = np.linalg.norm(features, axis=1, keepdims=True)
    norm = np.where(norm < 1e-8, 1.0, norm)
    return (features / norm).astype(np.float32)


def compute_delta(features: np.ndarray) -> np.ndarray:
    """First-order temporal difference; first frame is zero."""
    if features.shape[0] <= 1:
        return np.zeros_like(features, dtype=np.float32)
    delta = np.diff(features, axis=0, prepend=features[:1])
    return delta.astype(np.float32)


def context_mean(
    features: np.ndarray,
    context_frames: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Sliding mean with stride 1; returns (context_features, center_frame_indices)."""
    if context_frames <= 1 or features.shape[0] == 0:
        centers = np.arange(features.shape[0], dtype=np.int32)
        return features.astype(np.float32), centers
    if context_frames >= features.shape[0]:
        context_frames = max(1, features.shape[0])
    half = context_frames // 2
    out: list[np.ndarray] = []
    centers: list[int] = []
    for start in range(0, features.shape[0] - context_frames + 1):
        out.append(features[start : start + context_frames].mean(axis=0))
        centers.append(start + half)
    return np.asarray(out, dtype=np.float32), np.asarray(centers, dtype=np.int32)


def audio_to_pitch_sequence(
    audio: np.ndarray,
    sample_rate: int,
    config: PitchFeatureConfig,
) -> PitchSequence:
    """Extract pitch feature sequence with center-frame mapping."""
    feat = extract_chroma_cqt(audio, sample_rate, config)
    centers = np.arange(feat.shape[0], dtype=np.int32)
    feat = smooth_chroma(feat, config.smooth_frames)
    if config.normalize_per_frame:
        feat = l2_normalize_frames(feat)
    if config.use_delta:
        delta = compute_delta(feat)
        feat = np.concatenate([feat, delta], axis=1)
    if config.context_sec > 0:
        context_frames = max(1, int(round(config.context_sec * sample_rate / config.hop_length)))
        feat, centers = context_mean(feat, context_frames)
    duration_sec = len(audio) / sample_rate
    return PitchSequence(
        features=feat.astype(np.float32),
        center_frames=centers,
        sample_rate=sample_rate,
        hop_length=config.hop_length,
        duration_sec=duration_sec,
    )


def audio_to_pitch_frames(
    audio: np.ndarray,
    sample_rate: int,
    config: PitchFeatureConfig,
) -> np.ndarray:
    """Extract pitch feature matrix [T, D] (legacy API)."""
    return audio_to_pitch_sequence(audio, sample_rate, config).features


def clip_to_pitch_sequence(
    audio: np.ndarray,
    sample_rate: int,
    *,
    preprocess_config: PreprocessConfig | None = None,
    pitch_config: PitchFeatureConfig | None = None,
) -> PitchSequence:
    """Preprocess a waveform clip, then extract pitch features."""
    pre = preprocess_config or pitch_preprocess_config()
    pitch = pitch_config or PitchFeatureConfig()
    y = audio.astype(np.float32)
    sr = int(sample_rate)
    if sr != pre.sample_rate:
        y = librosa.resample(y, orig_sr=sr, target_sr=pre.sample_rate).astype(np.float32)
        sr = pre.sample_rate
    processed, sr = apply_preprocess(y, sr, pre)
    return audio_to_pitch_sequence(processed, sr, pitch)


def wav_to_pitch_sequence(
    path: Path,
    *,
    preprocess_config: PreprocessConfig | None = None,
    pitch_config: PitchFeatureConfig | None = None,
    start_sec: float = 0.0,
) -> PitchSequence:
    """Load WAV, preprocess, extract pitch sequence with centers."""
    cfg = pitch_config or PitchFeatureConfig()
    audio, sr, duration = load_and_preprocess_for_pitch(
        path,
        start_sec=start_sec,
        config=preprocess_config,
    )
    seq = audio_to_pitch_sequence(audio, sr, cfg)
    return PitchSequence(
        features=seq.features,
        center_frames=seq.center_frames,
        sample_rate=sr,
        hop_length=cfg.hop_length,
        duration_sec=duration,
    )


def wav_to_pitch(
    path: Path,
    *,
    preprocess_config: PreprocessConfig | None = None,
    pitch_config: PitchFeatureConfig | None = None,
    start_sec: float = 0.0,
) -> tuple[np.ndarray, float, int]:
    """Load WAV, preprocess, extract pitch frames (legacy API)."""
    seq = wav_to_pitch_sequence(
        path,
        preprocess_config=preprocess_config,
        pitch_config=pitch_config,
        start_sec=start_sec,
    )
    return seq.features, seq.duration_sec, seq.sample_rate
