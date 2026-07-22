"""Rhythm recognition: onset + duration + judgement (docs/05)."""

from music_practice.rhythm.config import OnsetDetectConfig, RhythmJudgeConfig
from music_practice.rhythm.duration import DurationMeasure, measure_duration
from music_practice.rhythm.judge import ExpectedNote, RhythmSegment, judge_notes
from music_practice.rhythm.onset import detect_onsets, detect_onsets_audio
from music_practice.rhythm.pipeline import evaluate_rhythm, evaluate_rhythm_from_track
from music_practice.rhythm.session import RhythmSession

__all__ = [
    "DurationMeasure",
    "ExpectedNote",
    "OnsetDetectConfig",
    "RhythmJudgeConfig",
    "RhythmSegment",
    "RhythmSession",
    "detect_onsets",
    "detect_onsets_audio",
    "evaluate_rhythm",
    "evaluate_rhythm_from_track",
    "judge_notes",
    "measure_duration",
]
