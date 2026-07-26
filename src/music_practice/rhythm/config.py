"""Rhythm detection / judgement configuration (docs/05 §6.3.7)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from music_practice.pitch.config import PitchDetectConfig

# How duration windows are placed on the practice timeline.
# - detected_onset: [assigned_onset_i, assigned_onset_{i+1}) from spectral-flux peaks
# - score_grid: [expected.onset_i, expected.onset_{i+1}) after first-note lock
# - anchored_grid: standard expected times after start-DTW lock; each note uses
#   [expected - pre, expected + duration + post], combined with detected onset
DurationWindowMode = Literal["detected_onset", "score_grid", "anchored_grid"]


@dataclass(frozen=True)
class OnsetDetectConfig:
    """Spectral-flux onset detection (OnsetDectection PeakDetector defaults)."""

    sample_rate: int = 22050
    frame_size: int = 512
    use_hamming: bool = True
    threshold_window_size: int = 10
    multiplier: float = 1.6
    # Drop peaks whose filtered flux is below this (silence / noise).
    min_peak_strength: float = 1e-4

    @property
    def hop_size(self) -> int:
        return self.frame_size

    @property
    def window_duration_sec(self) -> float:
        return self.frame_size / self.sample_rate

    @classmethod
    def for_tempo(cls, tempo: float, *, sample_rate: int = 22050) -> OnsetDetectConfig:
        pitch_cfg = PitchDetectConfig.for_tempo(tempo, sample_rate=sample_rate)
        return cls(sample_rate=pitch_cfg.sample_rate, frame_size=pitch_cfg.frame_size)


@dataclass(frozen=True)
class RhythmJudgeConfig:
    """Correctness thresholds for onset + duration (docs/05 §6.3)."""

    onset_tolerance_beat: float = 0.35
    onset_tolerance_sec_cap: float = 0.25
    use_ioi_after_first: bool = True
    duration_trim_ratio: float = 0.15
    duration_pitch_tolerance_semitone: float = 1.0
    duration_half_or_longer_ratio_min: float = 0.8
    duration_quarter_ratio_min: float = 0.5
    duration_ratio_max: float | None = None
    # detected_onset: duration windows from assigned spectral-flux peaks
    # score_grid: always use expected.onset (detected onsets are diagnostic only)
    # anchored_grid: expected timeline after start lock, with pre/post pads; detected
    # onset recenters the local search when it falls near the expected start.
    duration_window_mode: DurationWindowMode = "detected_onset"
    # Pads around each note's standard expected onset (in beats).
    grid_pre_beat: float = 0.2
    grid_post_beat: float = 0.35

    def onset_tolerance_sec(self, tempo_bpm: float) -> float:
        beat_sec = 60.0 / tempo_bpm if tempo_bpm > 0 else 0.5
        return min(self.onset_tolerance_beat * beat_sec, self.onset_tolerance_sec_cap)

    def quarter_sec(self, tempo_bpm: float) -> float:
        return 60.0 / tempo_bpm if tempo_bpm > 0 else 0.5

    def beat_sec(self, tempo_bpm: float) -> float:
        return 60.0 / tempo_bpm if tempo_bpm > 0 else 0.5

    def grid_pre_sec(self, tempo_bpm: float) -> float:
        return max(0.0, self.grid_pre_beat * self.beat_sec(tempo_bpm))

    def grid_post_sec(self, tempo_bpm: float) -> float:
        return max(0.0, self.grid_post_beat * self.beat_sec(tempo_bpm))
