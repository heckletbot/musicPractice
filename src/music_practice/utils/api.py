"""Unified public API for score, pitch, start_detect, and rhythm modules."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np

from music_practice.models import Interval, ParsedNote, Score
from music_practice.pitch.config import PitchDetectConfig
from music_practice.pitch.detector import PitchTrack, detect_pitch_track
from music_practice.pitch.evaluator import PitchEstimate, estimate_pitch, estimate_pitch_from_track
from music_practice.rhythm.config import OnsetDetectConfig, RhythmJudgeConfig
from music_practice.rhythm.judge import ExpectedNote, RhythmSegment
from music_practice.rhythm.pipeline import evaluate_rhythm
from music_practice.score.import_score import import_musicxml
from music_practice.score.intervals import build_intervals, interval_id_for_measure
from music_practice.score.loader import load_score_from_musicxml
from music_practice.score.resolver import notes_in_measure, resolve_start_note
from music_practice.score.store import default_scores_dir, list_scores, load_score, save_score
from music_practice.start_detect import StartDetectContext, StartDetectResult, detect_start
from music_practice.types import ScoreListItemDict, ScoreSummaryDict, StartNoteRef


def import_score(
    musicxml_path: str | Path,
    *,
    scores_dir: Path | None = None,
    interval_measures: int = 4,
    default_tempo_bpm: float = 120.0,
    part_id: str | None = None,
    score_id: str | None = None,
    overwrite: bool = False,
) -> Score:
    return import_musicxml(
        musicxml_path,
        scores_dir=scores_dir,
        interval_measures=interval_measures,
        default_tempo_bpm=default_tempo_bpm,
        part_id=part_id,
        score_id=score_id,
        overwrite=overwrite,
    )


def get_score(score_id: str, *, scores_dir: Path | None = None) -> Score:
    return load_score(score_id, scores_dir=scores_dir)


def list_score_summaries(*, scores_dir: Path | None = None) -> list[ScoreListItemDict]:
    return list_scores(scores_dir=scores_dir)


def parse_score(
    musicxml_path: str | Path,
    *,
    interval_measures: int = 4,
    default_tempo_bpm: float = 120.0,
    part_id: str | None = None,
    score_id: str | None = None,
) -> Score:
    return load_score_from_musicxml(
        musicxml_path,
        interval_measures=interval_measures,
        default_tempo_bpm=default_tempo_bpm,
        part_id=part_id,
        score_id=score_id,
    )


def build_score_intervals(total_measures: int, measures_per_interval: int = 4) -> list[Interval]:
    return build_intervals(total_measures, measures_per_interval)


def measure_interval_id(measure: int, measures_per_interval: int) -> int:
    return interval_id_for_measure(measure, measures_per_interval)


def get_start_note(score: Score, ref: StartNoteRef) -> ParsedNote:
    return resolve_start_note(score, ref)


def analyze_pitch_track(
    wav_path: str | Path,
    *,
    tempo: float = 120.0,
    config: PitchDetectConfig | None = None,
) -> PitchTrack:
    return detect_pitch_track(wav_path, config=config, tempo=tempo)


def analyze_pitch_segment(
    wav_path: str | Path,
    time_start_sec: float,
    time_end_sec: float,
    *,
    tempo: float = 120.0,
    config: PitchDetectConfig | None = None,
) -> PitchEstimate:
    return estimate_pitch(
        wav_path,
        time_start_sec,
        time_end_sec,
        config=config,
        tempo=tempo,
    )


def analyze_pitch_segment_from_track(
    track: PitchTrack,
    time_start_sec: float,
    time_end_sec: float,
    *,
    a4_hz: float = 442.0,
) -> PitchEstimate:
    return estimate_pitch_from_track(track, time_start_sec, time_end_sec, a4_hz=a4_hz)


def score_summary(score: Score) -> ScoreSummaryDict:
    return score.to_summary()


def detect_start_note(
    score: Score,
    *,
    start_note: StartNoteRef,
    query_wav: str | Path,
    templates_dir: Path,
    template_id: str | None = None,
    score_template_map: Path | None = None,
    context: StartDetectContext | None = None,
) -> StartDetectResult:
    from music_practice.start_detect.mapping import resolve_template_id

    tid = resolve_template_id(
        score.score_id,
        template_id=template_id,
        map_path=score_template_map,
    )
    return detect_start(
        score,
        template_id=tid,
        start_note=start_note,
        query_wav=query_wav,
        templates_dir=templates_dir,
        context=context,
    )


def evaluate_rhythm_from_track(
    expected_notes: Sequence[ExpectedNote],
    detected_onsets: Sequence[float],
    track: PitchTrack,
    *,
    tempo_bpm: float = 120.0,
    judge_config: RhythmJudgeConfig | None = None,
) -> list[RhythmSegment]:
    """Inject onsets + pitch track and return rhythm segments."""
    from music_practice.rhythm.pipeline import evaluate_rhythm_from_track as _eval

    return _eval(
        expected_notes,
        detected_onsets,
        track,
        tempo_bpm=tempo_bpm,
        judge_config=judge_config,
    )


def evaluate_rhythm_audio(
    expected_notes: Sequence[ExpectedNote],
    *,
    tempo_bpm: float = 120.0,
    wav_path: str | Path | None = None,
    audio: np.ndarray | None = None,
    sample_rate: int | None = None,
    judge_config: RhythmJudgeConfig | None = None,
    onset_config: OnsetDetectConfig | None = None,
) -> list[RhythmSegment]:
    """Detect onsets + pitch from PCM/WAV and judge rhythm."""
    return evaluate_rhythm(
        expected_notes,
        tempo_bpm=tempo_bpm,
        wav_path=wav_path,
        audio=audio,
        sample_rate=sample_rate,
        judge_config=judge_config,
        onset_config=onset_config,
    )
