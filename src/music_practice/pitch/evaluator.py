"""Segment pitch summary (OnsetDectection PitchEvaluator.pitchEvaluate median)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from music_practice.pitch.config import PitchDetectConfig
from music_practice.pitch.convert import hz_to_midi, hz_to_pitch_name, midi_to_hz
from music_practice.pitch.detector import PitchTrack, detect_pitch_track


@dataclass
class PitchEstimate:
    time_start_sec: float
    time_end_sec: float
    pitch_midi: float
    pitch: str | None
    frequency_hz: float | None
    valid_frame_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "time_start_sec": self.time_start_sec,
            "time_end_sec": self.time_end_sec,
            "pitch_midi": self.pitch_midi,
            "pitch": self.pitch,
            "frequency_hz": self.frequency_hz,
            "valid_frame_count": self.valid_frame_count,
        }


def _median_midi(frames: list[float]) -> float:
    values = sorted(item for item in frames if item > 0)
    if not values:
        return -1.0
    mid = len(values) // 2
    if len(values) % 2 == 1:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2.0


def estimate_pitch_from_track(
    track: PitchTrack,
    time_start_sec: float,
    time_end_sec: float,
    *,
    a4_hz: float = 442.0,
) -> PitchEstimate:
    selected = [
        frame
        for frame in track.frames
        if time_start_sec <= frame.time_sec < time_end_sec and frame.voiced and frame.pitch_midi > 0
    ]
    median = _median_midi([frame.pitch_midi for frame in selected])
    hz = midi_to_hz(median, a4_hz=a4_hz) if median > 0 else None
    name = hz_to_pitch_name(hz, a4_hz=a4_hz) if hz else None
    return PitchEstimate(
        time_start_sec=time_start_sec,
        time_end_sec=time_end_sec,
        pitch_midi=median,
        pitch=name,
        frequency_hz=hz,
        valid_frame_count=len(selected),
    )


def estimate_pitch(
    wav_path: str | Path,
    time_start_sec: float,
    time_end_sec: float,
    *,
    config: PitchDetectConfig | None = None,
    tempo: float = 120.0,
) -> PitchEstimate:
    cfg = config or PitchDetectConfig.for_tempo(tempo)
    track = detect_pitch_track(wav_path, config=cfg, tempo=tempo)
    return estimate_pitch_from_track(track, time_start_sec, time_end_sec, a4_hz=cfg.a4_frequency_hz)
