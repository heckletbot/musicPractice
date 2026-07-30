"""Rhythm evaluation pipeline (inject or PCM)."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np

from music_practice.contract.bridge import coerce_pitch_track
from music_practice.pitch.config import PitchDetectConfig
from music_practice.pitch.detector import PitchTrack, detect_pitch, pitch_track_from_audio
from music_practice.rhythm.config import OnsetDetectConfig, RhythmJudgeConfig
from music_practice.rhythm.judge import ExpectedNote, RhythmSegment, judge_notes
from music_practice.rhythm.onset import detect_onsets, detect_onsets_audio


def _normalize_tempo(tempo_bpm: float | None) -> float:
    if tempo_bpm is None or tempo_bpm <= 0:
        return 120.0
    return float(tempo_bpm)


def evaluate_rhythm(
    expected_notes: Sequence[ExpectedNote],
    *,
    tempo_bpm: float = 120.0,
    detected_onsets: Sequence[float] | None = None,
    track: PitchTrack | None = None,
    audio: np.ndarray | None = None,
    sample_rate: int | None = None,
    wav_path: str | Path | None = None,
    judge_config: RhythmJudgeConfig | None = None,
    onset_config: OnsetDetectConfig | None = None,
) -> list[RhythmSegment]:
    """
    Evaluate rhythm for expected notes.

    Provide either ``detected_onsets`` + ``track`` (inject path), or PCM via
    ``audio`` / ``wav_path`` (detection path). If only PCM is given, pitch track
    and onsets are computed via ``pitch.detect_pitch`` (public API).
    """
    tempo = _normalize_tempo(tempo_bpm)
    jcfg = judge_config or RhythmJudgeConfig()
    ocfg = onset_config or OnsetDetectConfig.for_tempo(tempo)

    pitch_track = track
    onsets: list[float]

    if detected_onsets is not None and pitch_track is not None:
        onsets = list(detected_onsets)
    elif wav_path is not None:
        onsets = (
            list(detected_onsets)
            if detected_onsets is not None
            else detect_onsets(wav_path, config=ocfg, tempo=tempo)
        )
        if pitch_track is None:
            pitch_cfg = PitchDetectConfig.for_tempo(tempo, sample_rate=ocfg.sample_rate)
            pitch_track = coerce_pitch_track(
                detect_pitch(wav_path, tempo=tempo, config=pitch_cfg)
            )
    elif audio is not None:
        sr = sample_rate if sample_rate is not None else ocfg.sample_rate
        onsets = (
            list(detected_onsets)
            if detected_onsets is not None
            else detect_onsets_audio(audio, sample_rate=sr, config=ocfg, tempo=tempo)
        )
        if pitch_track is None:
            pitch_cfg = PitchDetectConfig.for_tempo(tempo, sample_rate=sr)
            pitch_track = coerce_pitch_track(
                detect_pitch(audio, sample_rate=sr, tempo=tempo, config=pitch_cfg)
            )
    else:
        raise ValueError("Provide (detected_onsets + track) or wav_path/audio")

    assert pitch_track is not None
    return judge_notes(
        expected_notes,
        onsets,
        pitch_track,
        tempo_bpm=tempo,
        config=jcfg,
    )


# Back-compat alias used by rhythm.session and older call sites.
_pitch_track_from_audio = pitch_track_from_audio


def evaluate_rhythm_from_track(
    expected_notes: Sequence[ExpectedNote],
    detected_onsets: Sequence[float],
    track: PitchTrack,
    *,
    tempo_bpm: float = 120.0,
    judge_config: RhythmJudgeConfig | None = None,
) -> list[RhythmSegment]:
    """Inject path: precomputed onsets + pitch track."""
    return evaluate_rhythm(
        expected_notes,
        tempo_bpm=tempo_bpm,
        detected_onsets=detected_onsets,
        track=track,
        judge_config=judge_config,
    )
