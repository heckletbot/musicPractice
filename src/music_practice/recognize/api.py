"""Unified recognize() entry: ScoreData + audio → per-note judgement."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np

from music_practice.contract.bridge import slice_practice_notes
from music_practice.contract.schema import RECOGNIZE_RESULT_SCHEMA, RECOGNIZE_RESULT_VERSION
from music_practice.contract.validate import validate_score_data
from music_practice.pitch.detector import PitchTrack
from music_practice.pitch.evaluator import estimate_pitch_from_track
from music_practice.rhythm.config import OnsetDetectConfig, RhythmJudgeConfig
from music_practice.rhythm.judge import ExpectedNote, RhythmSegment, judge_notes
from music_practice.rhythm.pipeline import evaluate_rhythm


def _decode_audio(audio_data: bytes | np.ndarray) -> np.ndarray:
    if isinstance(audio_data, np.ndarray):
        arr = np.asarray(audio_data, dtype=np.float32).reshape(-1)
        return arr
    if not isinstance(audio_data, (bytes, bytearray, memoryview)):
        raise TypeError("audio_data must be float32 bytes or numpy ndarray")
    arr = np.frombuffer(audio_data, dtype=np.float32)
    if arr.size == 0:
        raise ValueError("audio_data is empty")
    return np.asarray(arr, dtype=np.float32)


def _judge_config_from_dict(config: Mapping[str, Any] | None) -> RhythmJudgeConfig:
    cfg = dict(config or {})
    mode = cfg.get("duration_window_mode", "anchored_grid")
    return RhythmJudgeConfig(
        onset_tolerance_beat=float(cfg.get("onset_tolerance_beat", 0.35)),
        onset_tolerance_sec_cap=float(cfg.get("onset_tolerance_sec_cap", 0.25)),
        duration_pitch_tolerance_semitone=float(cfg.get("pitch_tolerance_semitones", 1.0)),
        duration_window_mode=mode,  # type: ignore[arg-type]
    )


def _expected_from_practice_notes(notes: Sequence[Mapping[str, Any]]) -> list[ExpectedNote]:
    out: list[ExpectedNote] = []
    for note in notes:
        if note.get("is_rest"):
            continue
        midi = note.get("pitch_midi")
        if midi is None:
            raise ValueError(
                f"note measure={note.get('measure')} index={note.get('note_index_in_measure')} "
                "missing pitch_midi (required for recognize)"
            )
        out.append(
            ExpectedNote(
                onset_sec=float(note["onset"]),
                duration_sec=float(note["duration"]),
                pitch_midi=float(midi),
                measure=int(note["measure"]),
                note_index_in_measure=int(note["note_index_in_measure"]),
                is_rest=False,
            )
        )
    return out


def _pitch_ok(
    *,
    expected_midi: float,
    detected_midi: float | None,
    tolerance: float,
) -> bool:
    if detected_midi is None or detected_midi < 0:
        return False
    return abs(float(detected_midi) - float(expected_midi)) <= float(tolerance)


def _build_note_result(
    seg: RhythmSegment,
    *,
    pitch_expected: float,
    pitch_detected: float | None,
    pitch_ok: bool,
) -> dict[str, Any]:
    note_ref = seg.note_ref or {}
    missed = seg.onset_detected_sec is None and seg.valid_frame_count == 0
    rhythm_ok = bool(seg.rhythm_ok)
    overall = bool(pitch_ok and rhythm_ok and not missed)
    error_dims: list[str] = []
    if missed:
        error_dims.append("missed")
    if not seg.onset_ok:
        error_dims.append("onset")
    if not seg.duration_ok:
        error_dims.append("duration")
    if not pitch_ok:
        error_dims.append("pitch")
    return {
        "measure": note_ref.get("measure"),
        "note_index_in_measure": note_ref.get("note_index_in_measure"),
        "onset_expected_sec": seg.onset_expected_sec,
        "onset_detected_sec": seg.onset_detected_sec,
        "onset_ok": bool(seg.onset_ok),
        "duration_expected_sec": seg.duration_expected_sec,
        "duration_detected_sec": seg.duration_detected_sec,
        "duration_ok": bool(seg.duration_ok),
        "pitch_expected_midi": float(pitch_expected),
        "pitch_detected_midi": None if pitch_detected is None else float(pitch_detected),
        "pitch_ok": bool(pitch_ok),
        "rhythm_ok": rhythm_ok,
        "overall_correct": overall,
        "error_dims": error_dims,
    }


def _summarize(notes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total = len(notes)
    correct = sum(1 for n in notes if n.get("overall_correct"))
    return {
        "total_notes": total,
        "correct_count": correct,
        "onset_error_count": sum(1 for n in notes if not n.get("onset_ok")),
        "duration_error_count": sum(1 for n in notes if not n.get("duration_ok")),
        "pitch_error_count": sum(1 for n in notes if not n.get("pitch_ok")),
        "missed_count": sum(1 for n in notes if "missed" in (n.get("error_dims") or [])),
        "accuracy": (correct / total) if total else 0.0,
    }


def recognize_from_track(
    score_data: Mapping[str, Any],
    *,
    detected_onsets: Sequence[float],
    track: PitchTrack,
    start_from: Mapping[str, Any] | None = None,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Inject path for tests / offline: ScoreData + onsets + PitchTrack → RecognizeResult."""
    validated = validate_score_data(score_data)
    practice_notes, resolved_start = slice_practice_notes(validated, start_from)
    expected = _expected_from_practice_notes(practice_notes)
    jcfg = _judge_config_from_dict(config)
    tempo = float(validated["tempo"])
    segs = judge_notes(expected, detected_onsets, track, tempo_bpm=tempo, config=jcfg)
    tol = float((config or {}).get("pitch_tolerance_semitones", jcfg.duration_pitch_tolerance_semitone))

    out_notes: list[dict[str, Any]] = []
    for exp, seg in zip(expected, segs):
        t0 = seg.onset_detected_sec if seg.onset_detected_sec is not None else seg.onset_expected_sec
        t1 = t0 + max(seg.duration_detected_sec, 1e-3)
        est = estimate_pitch_from_track(track, t0, t1)
        detected = est.pitch_midi if est.valid_frame_count > 0 and est.pitch_midi > 0 else None
        pok = _pitch_ok(expected_midi=exp.pitch_midi, detected_midi=detected, tolerance=tol)
        out_notes.append(
            _build_note_result(
                seg,
                pitch_expected=exp.pitch_midi,
                pitch_detected=detected,
                pitch_ok=pok,
            )
        )

    return {
        "schema": RECOGNIZE_RESULT_SCHEMA,
        "schema_version": RECOGNIZE_RESULT_VERSION,
        "summary": _summarize(out_notes),
        "notes": out_notes,
        "start_from": resolved_start,
    }


def recognize(
    score_data: Mapping[str, Any],
    audio_data: bytes | np.ndarray,
    sample_rate: int,
    start_from: Mapping[str, Any] | None = None,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Recognize practice performance against ScoreData (no MusicXML).

    ``audio_data``: float32 mono PCM as bytes (``ndarray.tobytes()``) or ndarray.
    """
    validated = validate_score_data(score_data)
    practice_notes, resolved_start = slice_practice_notes(validated, start_from)
    expected = _expected_from_practice_notes(practice_notes)
    if not expected:
        return {
            "schema": RECOGNIZE_RESULT_SCHEMA,
            "schema_version": RECOGNIZE_RESULT_VERSION,
            "summary": _summarize([]),
            "notes": [],
            "start_from": resolved_start,
        }

    audio = _decode_audio(audio_data)
    jcfg = _judge_config_from_dict(config)
    tempo = float(validated["tempo"])
    sr = int(sample_rate)
    ocfg = OnsetDetectConfig.for_tempo(tempo, sample_rate=sr)
    segs = evaluate_rhythm(
        expected,
        tempo_bpm=tempo,
        audio=audio,
        sample_rate=sr,
        judge_config=jcfg,
        onset_config=ocfg,
    )

    # Rebuild a pitch track for pitch_ok fields (evaluate_rhythm already ran pyin internally;
    # re-run for explicit per-note MIDI to keep the public contract stable).
    from music_practice.pitch.config import PitchDetectConfig
    from music_practice.rhythm.pipeline import _pitch_track_from_audio

    pitch_cfg = PitchDetectConfig.for_tempo(tempo, sample_rate=sr)
    track = _pitch_track_from_audio(audio, pitch_cfg)
    tol = float((config or {}).get("pitch_tolerance_semitones", jcfg.duration_pitch_tolerance_semitone))

    out_notes: list[dict[str, Any]] = []
    for exp, seg in zip(expected, segs):
        t0 = seg.onset_detected_sec if seg.onset_detected_sec is not None else seg.onset_expected_sec
        t1 = t0 + max(seg.duration_detected_sec, 1e-3)
        est = estimate_pitch_from_track(track, t0, t1)
        detected = est.pitch_midi if est.valid_frame_count > 0 and est.pitch_midi > 0 else None
        pok = _pitch_ok(expected_midi=exp.pitch_midi, detected_midi=detected, tolerance=tol)
        out_notes.append(
            _build_note_result(
                seg,
                pitch_expected=exp.pitch_midi,
                pitch_detected=detected,
                pitch_ok=pok,
            )
        )

    return {
        "schema": RECOGNIZE_RESULT_SCHEMA,
        "schema_version": RECOGNIZE_RESULT_VERSION,
        "summary": _summarize(out_notes),
        "notes": out_notes,
        "start_from": resolved_start,
    }