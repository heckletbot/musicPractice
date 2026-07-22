"""Pitch detection configuration (OnsetDectection 实时识别设置)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PitchDetectConfig:
    sample_rate: int = 22050
    frame_size: int = 512
    a4_frequency_hz: float = 442.0
    fmin_hz: float = 65.0
    fmax_hz: float = 2093.0

    @property
    def window_duration_sec(self) -> float:
        return self.frame_size / self.sample_rate

    @classmethod
    def for_tempo(cls, tempo: float, *, sample_rate: int = 22050) -> PitchDetectConfig:
        frame_size = 512 if tempo >= 120 else 1024
        return cls(sample_rate=sample_rate, frame_size=frame_size)
