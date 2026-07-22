"""Rhythm evaluation pipeline (inject or PCM)."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np

from music_practice.pitch.config import PitchDetectConfig
from music_practice.pitch.detector import PitchTrack, detect_pitch_track
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
    and onsets are computed automatically.
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
            pitch_track = detect_pitch_track(wav_path, config=pitch_cfg, tempo=tempo)
    elif audio is not None:
        sr = sample_rate if sample_rate is not None else ocfg.sample_rate
        onsets = (
            list(detected_onsets)
            if detected_onsets is not None
            else detect_onsets_audio(audio, sample_rate=sr, config=ocfg, tempo=tempo)
        )
        if pitch_track is None:
            # Build pitch track via temporary path-free path: reuse detect on mono buffer.
            from music_practice.pitch.detector import PitchFrame

            pitch_cfg = PitchDetectConfig.for_tempo(tempo, sample_rate=sr)
            pitch_track = _pitch_track_from_audio(audio, pitch_cfg)
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


def _pitch_track_from_audio(audio: np.ndarray, cfg: PitchDetectConfig) -> PitchTrack:
    """Frame-wise pitch for in-memory PCM (same hop policy as detect_pitch_track)."""
    import librosa

    from music_practice.pitch.convert import hz_to_midi, hz_to_pitch_name
    from music_practice.pitch.detector import PitchFrame

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
