"""Frame-wise pitch detection (OnsetDectection FastYinMethod + PitchEvaluator)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import soundfile as sf

from music_practice.contract.bridge import pitch_track_to_pitch_track_data
from music_practice.pitch.config import PitchDetectConfig
from music_practice.pitch.convert import hz_to_midi, hz_to_pitch_name


@dataclass
class PitchFrame:
    time_sec: float
    frequency_hz: float | None
    pitch_midi: float
    pitch: str | None
    voiced: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "time_sec": self.time_sec,
            "frequency_hz": self.frequency_hz,
            "pitch_midi": self.pitch_midi,
            "pitch": self.pitch,
            "voiced": self.voiced,
        }


@dataclass
class PitchTrack:
    sample_rate: int
    frame_size: int
    window_duration_sec: float
    frames: list[PitchFrame] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_rate": self.sample_rate,
            "frame_size": self.frame_size,
            "window_duration_sec": self.window_duration_sec,
            "frames": [item.to_dict() for item in self.frames],
        }


def _load_mono(path: Path, target_sr: int) -> np.ndarray:
    audio, sr = sf.read(str(path), always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != target_sr:
        audio = librosa.resample(audio.astype(np.float64), orig_sr=sr, target_sr=target_sr)
    return audio.astype(np.float32)


def pitch_track_from_audio(audio: np.ndarray, cfg: PitchDetectConfig) -> PitchTrack:
    """Frame-wise pitch for in-memory PCM (same hop policy as detect_pitch_track)."""
    audio_f = np.asarray(audio, dtype=np.float32)
    if audio_f.size < cfg.frame_size:
        return PitchTrack(
            sample_rate=cfg.sample_rate,
            frame_size=cfg.frame_size,
            window_duration_sec=cfg.window_duration_sec,
            frames=[],
        )

    f0, voiced_flag, _ = librosa.pyin(
        audio_f,
        fmin=cfg.fmin_hz,
        fmax=cfg.fmax_hz,
        sr=cfg.sample_rate,
        frame_length=cfg.frame_size,
        hop_length=cfg.frame_size,
        center=False,
    )
    frames: list[PitchFrame] = []
    for i, hz_raw in enumerate(f0):
        voiced = bool(voiced_flag[i]) if voiced_flag is not None else False
        hz = float(hz_raw) if voiced and hz_raw is not None and np.isfinite(hz_raw) else None
        midi = hz_to_midi(hz, a4_hz=cfg.a4_frequency_hz) if hz is not None else -1.0
        name = hz_to_pitch_name(hz, a4_hz=cfg.a4_frequency_hz) if hz is not None else None
        frames.append(
            PitchFrame(
                time_sec=i * cfg.window_duration_sec,
                frequency_hz=hz,
                pitch_midi=midi if hz is not None else -1.0,
                pitch=name,
                voiced=hz is not None,
            )
        )
    return PitchTrack(
        sample_rate=cfg.sample_rate,
        frame_size=cfg.frame_size,
        window_duration_sec=cfg.window_duration_sec,
        frames=frames,
    )


def detect_pitch_track(
    wav_path: str | Path,
    *,
    config: PitchDetectConfig | None = None,
    tempo: float = 120.0,
) -> PitchTrack:
    """Detect pitch frame-by-frame (non-overlapping hops, aligned with Java PitchEvaluator)."""
    cfg = config or PitchDetectConfig.for_tempo(tempo)
    audio = _load_mono(Path(wav_path), cfg.sample_rate)
    if audio.size < cfg.frame_size:
        return PitchTrack(
            sample_rate=cfg.sample_rate,
            frame_size=cfg.frame_size,
            window_duration_sec=cfg.window_duration_sec,
            frames=[],
        )

    f0, voiced_flag, _ = librosa.pyin(
        audio,
        fmin=cfg.fmin_hz,
        fmax=cfg.fmax_hz,
        sr=cfg.sample_rate,
        frame_length=cfg.frame_size,
        hop_length=cfg.frame_size,
        fill_na=np.nan,
    )

    frames: list[PitchFrame] = []
    for index, (freq, voiced) in enumerate(zip(f0, voiced_flag, strict=False)):
        time_sec = index * cfg.window_duration_sec
        is_voiced = bool(voiced) and not (freq is None or np.isnan(freq))
        hz = float(freq) if is_voiced else None
        midi = hz_to_midi(hz, a4_hz=cfg.a4_frequency_hz) if hz is not None else -1.0
        name = hz_to_pitch_name(hz, a4_hz=cfg.a4_frequency_hz) if hz is not None else None
        frames.append(
            PitchFrame(
                time_sec=time_sec,
                frequency_hz=hz,
                pitch_midi=midi,
                pitch=name,
                voiced=is_voiced,
            )
        )

    return PitchTrack(
        sample_rate=cfg.sample_rate,
        frame_size=cfg.frame_size,
        window_duration_sec=cfg.window_duration_sec,
        frames=frames,
    )


def detect_pitch(
    audio: str | Path | np.ndarray,
    *,
    sample_rate: int | None = None,
    tempo: float = 120.0,
    config: PitchDetectConfig | None = None,
) -> dict[str, Any]:
    """Public pitch API: path or float32 PCM → validated PitchTrackData dict."""
    if config is None:
        cfg = PitchDetectConfig.for_tempo(tempo, sample_rate=sample_rate or 22050)
    elif sample_rate is not None and int(sample_rate) != int(config.sample_rate):
        cfg = PitchDetectConfig(
            sample_rate=int(sample_rate),
            frame_size=config.frame_size,
            a4_frequency_hz=config.a4_frequency_hz,
            fmin_hz=config.fmin_hz,
            fmax_hz=config.fmax_hz,
        )
    else:
        cfg = config

    if isinstance(audio, (str, Path)):
        track = detect_pitch_track(audio, config=cfg, tempo=tempo)
    else:
        track = pitch_track_from_audio(np.asarray(audio, dtype=np.float32), cfg)
    return pitch_track_to_pitch_track_data(track)
