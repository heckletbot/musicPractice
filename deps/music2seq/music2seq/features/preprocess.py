"""Waveform preprocessing before feature extraction."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import librosa
import numpy as np
from scipy.signal import butter, sosfiltfilt

from music2seq.features.extractor import load_audio_mono


@dataclass(frozen=True)
class PreprocessConfig:
    sample_rate: int = 22050
    highpass_hz: float | None = 80.0
    trim_top_db: float | None = 30.0
    target_rms: float | None = 0.05
    use_harmonic: bool = False
    bandpass_low_hz: float | None = None
    bandpass_high_hz: float | None = None
    peak_limit: float = 0.98

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PreprocessConfig:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def pitch_preprocess_config() -> PreprocessConfig:
    """Preset for pitch feature extraction: harmonic + bandpass."""
    return PreprocessConfig(
        highpass_hz=80.0,
        trim_top_db=None,
        target_rms=0.05,
        use_harmonic=True,
        bandpass_low_hz=150.0,
        bandpass_high_hz=3500.0,
        peak_limit=0.98,
    )


def _highpass(audio: np.ndarray, sample_rate: int, cutoff_hz: float) -> np.ndarray:
    nyquist = sample_rate / 2.0
    freq = min(cutoff_hz, nyquist * 0.95)
    sos = butter(5, freq, btype="high", fs=sample_rate, output="sos")
    return sosfiltfilt(sos, audio).astype(np.float32)


def _bandpass(
    audio: np.ndarray,
    sample_rate: int,
    low_hz: float,
    high_hz: float,
) -> np.ndarray:
    nyquist = sample_rate / 2.0
    low = min(max(low_hz, 1.0), nyquist * 0.95)
    high = min(max(high_hz, low + 1.0), nyquist * 0.99)
    sos = butter(5, [low, high], btype="band", fs=sample_rate, output="sos")
    return sosfiltfilt(sos, audio).astype(np.float32)


def _trim_silence(audio: np.ndarray, sample_rate: int, top_db: float) -> np.ndarray:
    trimmed, _ = librosa.effects.trim(audio, top_db=top_db)
    if trimmed.size == 0:
        return audio
    return trimmed.astype(np.float32)


def _normalize_rms(audio: np.ndarray, target_rms: float) -> np.ndarray:
    rms = float(np.sqrt(np.mean(audio**2))) + 1e-8
    return (audio * (target_rms / rms)).astype(np.float32)


def _limit_peak(audio: np.ndarray, peak_limit: float) -> np.ndarray:
    peak = float(np.max(np.abs(audio)))
    if peak <= peak_limit or peak < 1e-8:
        return audio
    return (audio * (peak_limit / peak)).astype(np.float32)


def _extract_harmonic(audio: np.ndarray, *, chunk_sec: float = 30.0, sample_rate: int = 22050) -> np.ndarray:
    # librosa.effects.harmonic is much lighter than full HPSS for long audio.
    if len(audio) > int(chunk_sec * sample_rate * 4):
        return librosa.effects.harmonic(audio).astype(np.float32)
    chunk_samples = max(sample_rate, int(chunk_sec * sample_rate))
    if len(audio) <= chunk_samples:
        harmonic, _ = librosa.effects.hpss(audio)
        return harmonic.astype(np.float32)
    out = np.zeros_like(audio, dtype=np.float32)
    for start in range(0, len(audio), chunk_samples):
        end = min(len(audio), start + chunk_samples)
        harmonic, _ = librosa.effects.hpss(audio[start:end])
        out[start:end] = harmonic.astype(np.float32)
    return out


def apply_preprocess(
    audio: np.ndarray,
    sample_rate: int,
    config: PreprocessConfig,
) -> tuple[np.ndarray, int]:
    """Apply configured preprocessing chain; returns (audio, sample_rate)."""
    y = audio.astype(np.float32)
    sr = int(sample_rate)

    if config.highpass_hz is not None and config.highpass_hz > 0:
        y = _highpass(y, sr, config.highpass_hz)

    if config.trim_top_db is not None:
        y = _trim_silence(y, sr, config.trim_top_db)

    if config.use_harmonic:
        # Full HPSS/harmonic on 5+ minute audio can OOM in constrained environments.
        if len(y) <= sr * 120:
            y = _extract_harmonic(y, sample_rate=sr)

    if (
        config.bandpass_low_hz is not None
        and config.bandpass_high_hz is not None
        and config.bandpass_high_hz > config.bandpass_low_hz
    ):
        y = _bandpass(y, sr, config.bandpass_low_hz, config.bandpass_high_hz)

    if config.target_rms is not None and config.target_rms > 0:
        y = _normalize_rms(y, config.target_rms)

    y = _limit_peak(y, config.peak_limit)
    return y, sr


def load_and_preprocess(
    path: str | Path,
    config: PreprocessConfig | None = None,
    *,
    start_sec: float = 0.0,
) -> tuple[np.ndarray, int, float]:
    """Load audio file, resample, optional leading trim, preprocess; return (audio, sr, duration_sec)."""
    cfg = config or PreprocessConfig()
    audio, sr = load_audio_mono(Path(path), cfg.sample_rate)
    if start_sec > 0:
        offset = int(round(start_sec * sr))
        if offset >= len(audio):
            raise ValueError(f"start_sec={start_sec} 超出音频长度 {len(audio)/sr:.3f}s")
        audio = audio[offset:]
    processed, sr = apply_preprocess(audio, sr, cfg)
    duration = len(processed) / sr
    return processed, sr, duration


def load_and_preprocess_for_pitch(
    path: str | Path,
    *,
    start_sec: float = 0.0,
    config: PreprocessConfig | None = None,
) -> tuple[np.ndarray, int, float]:
    """Load and apply pitch-oriented preprocessing preset."""
    cfg = config or pitch_preprocess_config()
    return load_and_preprocess(path, cfg, start_sec=start_sec)
