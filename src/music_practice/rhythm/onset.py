"""Spectral-flux onset detection (OnsetDectection SpectralDifference + PeakDetector)."""

from __future__ import annotations

from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from music_practice.rhythm.config import OnsetDetectConfig


def _load_mono(path: Path, target_sr: int) -> np.ndarray:
    audio, sr = sf.read(str(path), always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != target_sr:
        audio = librosa.resample(audio.astype(np.float64), orig_sr=sr, target_sr=target_sr)
    return audio.astype(np.float32)


def spectral_flux(
    audio: np.ndarray,
    *,
    sample_rate: int,
    frame_size: int,
    hop_size: int | None = None,
    use_hamming: bool = True,
) -> np.ndarray:
    """Half-wave-rectified spectral flux per analysis frame (hop = frame_size by default)."""
    hop = hop_size if hop_size is not None else frame_size
    if audio.size < frame_size:
        return np.zeros(0, dtype=np.float64)

    window = "hamming" if use_hamming else None
    # center=False aligns frame i to time i * hop / sr (Java PeakDetector style).
    stft = librosa.stft(
        audio.astype(np.float64),
        n_fft=frame_size,
        hop_length=hop,
        win_length=frame_size,
        window=window if window else "boxcar",
        center=False,
    )
    mag = np.abs(stft)
    if mag.shape[1] == 0:
        return np.zeros(0, dtype=np.float64)

    flux = np.zeros(mag.shape[1], dtype=np.float64)
    prev = np.zeros(mag.shape[0], dtype=np.float64)
    for i in range(mag.shape[1]):
        diff = mag[:, i] - prev
        flux[i] = float(np.sum(np.maximum(diff, 0.0)))
        prev = mag[:, i]
    return flux


def detect_peaks(
    spectral_flux_values: np.ndarray,
    *,
    threshold_window_size: int = 10,
    multiplier: float = 1.6,
    min_peak_strength: float = 1e-4,
) -> list[int]:
    """Return frame indices of peaks (OnsetDectection PeakDetector)."""
    flux = np.asarray(spectral_flux_values, dtype=np.float64)
    n = flux.size
    if n < 2:
        return []

    threshold = np.zeros(n, dtype=np.float64)
    for i in range(n):
        start = max(0, i - threshold_window_size)
        end = min(n - 1, i + threshold_window_size)
        mean = float(np.mean(flux[start : end + 1]))
        threshold[i] = mean * multiplier

    filtered = np.maximum(flux - threshold, 0.0)
    # Java: peak if filtered[i] > filtered[i+1]; peaks length is n-1
    peaks: list[int] = []
    for i in range(n - 1):
        if filtered[i] > filtered[i + 1] and filtered[i] >= min_peak_strength:
            peaks.append(i)
    return peaks


def peaks_to_onsets(
    peak_frames: list[int],
    *,
    hop_size: int,
    sample_rate: int,
) -> list[float]:
    return [frame * hop_size / sample_rate for frame in peak_frames]


def detect_onsets_audio(
    audio: np.ndarray,
    *,
    sample_rate: int | None = None,
    config: OnsetDetectConfig | None = None,
    tempo: float = 120.0,
) -> list[float]:
    """Detect onset times (seconds) from mono PCM."""
    cfg = config or OnsetDetectConfig.for_tempo(tempo)
    sr = sample_rate if sample_rate is not None else cfg.sample_rate
    if sr != cfg.sample_rate and sample_rate is not None:
        # Keep caller's sr; rebuild frame params from tempo only when using defaults.
        pass
    frame_size = cfg.frame_size
    hop = cfg.hop_size

    flux = spectral_flux(
        np.asarray(audio, dtype=np.float32),
        sample_rate=sr,
        frame_size=frame_size,
        hop_size=hop,
        use_hamming=cfg.use_hamming,
    )
    peaks = detect_peaks(
        flux,
        threshold_window_size=cfg.threshold_window_size,
        multiplier=cfg.multiplier,
        min_peak_strength=cfg.min_peak_strength,
    )
    return peaks_to_onsets(peaks, hop_size=hop, sample_rate=sr)


def detect_onsets(
    wav_path: str | Path,
    *,
    config: OnsetDetectConfig | None = None,
    tempo: float = 120.0,
) -> list[float]:
    cfg = config or OnsetDetectConfig.for_tempo(tempo)
    audio = _load_mono(Path(wav_path), cfg.sample_rate)
    return detect_onsets_audio(audio, sample_rate=cfg.sample_rate, config=cfg, tempo=tempo)
