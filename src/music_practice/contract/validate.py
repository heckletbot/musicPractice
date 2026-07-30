"""Validate and (de)serialize ScoreData / PitchTrackData."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from music_practice.contract.schema import (
    PITCH_TRACK_DATA_SCHEMA,
    PITCH_TRACK_DATA_VERSION,
    SCORE_DATA_SCHEMA,
    SCORE_DATA_VERSION,
    SUPPORTED_PITCH_TRACK_DATA_VERSIONS,
    SUPPORTED_SCORE_DATA_VERSIONS,
)


class ScoreDataError(ValueError):
    """ScoreData does not satisfy the fixed interface contract."""


class PitchTrackDataError(ValueError):
    """PitchTrackData does not satisfy the fixed interface contract."""


def validate_score_data(data: Mapping[str, Any], *, strict_schema: bool = True) -> dict[str, Any]:
    """Return a shallow-copied, validated ScoreData dict.

    Raises ``ScoreDataError`` on contract violations.
    """
    if not isinstance(data, Mapping):
        raise ScoreDataError("score_data must be a mapping")

    out = dict(data)
    schema = out.get("schema")
    version = out.get("schema_version")
    if strict_schema:
        if schema != SCORE_DATA_SCHEMA:
            raise ScoreDataError(f"schema must be {SCORE_DATA_SCHEMA!r}, got {schema!r}")
        if version not in SUPPORTED_SCORE_DATA_VERSIONS:
            raise ScoreDataError(
                f"unsupported schema_version {version!r}; "
                f"supported={sorted(SUPPORTED_SCORE_DATA_VERSIONS)}"
            )
    else:
        out.setdefault("schema", SCORE_DATA_SCHEMA)
        out.setdefault("schema_version", SCORE_DATA_VERSION)

    for key in (
        "score_id",
        "title",
        "tempo",
        "time_signature",
        "key",
        "total_measures",
        "interval_measures",
        "intervals",
        "notes",
    ):
        if key not in out:
            raise ScoreDataError(f"missing required field: {key}")

    try:
        tempo = float(out["tempo"])
    except (TypeError, ValueError) as exc:
        raise ScoreDataError("tempo must be a number") from exc
    if tempo <= 0:
        raise ScoreDataError("tempo must be > 0")
    out["tempo"] = tempo
    out["total_measures"] = int(out["total_measures"])
    out["interval_measures"] = int(out["interval_measures"])
    out["score_id"] = str(out["score_id"])
    out["title"] = str(out["title"])
    out["time_signature"] = str(out["time_signature"])
    out["key"] = str(out["key"])

    if not isinstance(out["intervals"], list):
        raise ScoreDataError("intervals must be a list")
    if not isinstance(out["notes"], list):
        raise ScoreDataError("notes must be a list")

    notes: list[dict[str, Any]] = []
    for i, raw in enumerate(out["notes"]):
        if not isinstance(raw, Mapping):
            raise ScoreDataError(f"notes[{i}] must be a mapping")
        note = dict(raw)
        for req in (
            "pitch",
            "measure",
            "note_index_in_measure",
            "beat",
            "onset",
            "duration",
            "interval_id",
        ):
            if req not in note:
                raise ScoreDataError(f"notes[{i}] missing field: {req}")
        try:
            measure = int(note["measure"])
            note_index = int(note["note_index_in_measure"])
            beat = float(note["beat"])
            onset = float(note["onset"])
            duration = float(note["duration"])
            interval_id = int(note["interval_id"])
        except (TypeError, ValueError) as exc:
            raise ScoreDataError(f"notes[{i}] has invalid numeric fields") from exc
        if measure < 1:
            raise ScoreDataError(f"notes[{i}].measure must be >= 1")
        if note_index < 1:
            raise ScoreDataError(f"notes[{i}].note_index_in_measure must be >= 1")
        if duration <= 0:
            raise ScoreDataError(f"notes[{i}].duration must be > 0")
        pitch_midi = note.get("pitch_midi")
        if pitch_midi is not None:
            pitch_midi = float(pitch_midi)
        notes.append(
            {
                "pitch": str(note["pitch"]),
                "pitch_midi": pitch_midi,
                "measure": measure,
                "note_index_in_measure": note_index,
                "beat": beat,
                "onset": onset,
                "duration": duration,
                "interval_id": interval_id,
                "is_rest": bool(note.get("is_rest", False)),
            }
        )
    out["notes"] = notes

    intervals: list[dict[str, Any]] = []
    for i, raw in enumerate(out["intervals"]):
        if not isinstance(raw, Mapping):
            raise ScoreDataError(f"intervals[{i}] must be a mapping")
        item = dict(raw)
        for req in ("id", "start_measure", "end_measure", "note_count"):
            if req not in item:
                raise ScoreDataError(f"intervals[{i}] missing field: {req}")
        intervals.append(
            {
                "id": int(item["id"]),
                "start_measure": int(item["start_measure"]),
                "end_measure": int(item["end_measure"]),
                "note_count": int(item["note_count"]),
            }
        )
    out["intervals"] = intervals
    return out


def dump_score_data(data: Mapping[str, Any], path: str | Path, *, indent: int = 2) -> Path:
    validated = validate_score_data(data)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(validated, ensure_ascii=False, indent=indent), encoding="utf-8")
    return target


def load_score_data(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_score_data(payload)


def validate_pitch_track_data(
    data: Mapping[str, Any],
    *,
    strict_schema: bool = True,
) -> dict[str, Any]:
    """Return a shallow-copied, validated PitchTrackData dict.

    Raises ``PitchTrackDataError`` on contract violations.
    """
    if not isinstance(data, Mapping):
        raise PitchTrackDataError("pitch_track_data must be a mapping")

    out = dict(data)
    schema = out.get("schema")
    version = out.get("schema_version")
    if strict_schema:
        if schema != PITCH_TRACK_DATA_SCHEMA:
            raise PitchTrackDataError(
                f"schema must be {PITCH_TRACK_DATA_SCHEMA!r}, got {schema!r}"
            )
        if version not in SUPPORTED_PITCH_TRACK_DATA_VERSIONS:
            raise PitchTrackDataError(
                f"unsupported schema_version {version!r}; "
                f"supported={sorted(SUPPORTED_PITCH_TRACK_DATA_VERSIONS)}"
            )
    else:
        out.setdefault("schema", PITCH_TRACK_DATA_SCHEMA)
        out.setdefault("schema_version", PITCH_TRACK_DATA_VERSION)

    for key in ("sample_rate", "frame_size", "window_duration_sec", "frames"):
        if key not in out:
            raise PitchTrackDataError(f"missing required field: {key}")

    try:
        sample_rate = int(out["sample_rate"])
        frame_size = int(out["frame_size"])
        window_duration_sec = float(out["window_duration_sec"])
    except (TypeError, ValueError) as exc:
        raise PitchTrackDataError("sample_rate/frame_size/window_duration_sec invalid") from exc
    if sample_rate <= 0:
        raise PitchTrackDataError("sample_rate must be > 0")
    if frame_size <= 0:
        raise PitchTrackDataError("frame_size must be > 0")
    if window_duration_sec <= 0:
        raise PitchTrackDataError("window_duration_sec must be > 0")
    out["sample_rate"] = sample_rate
    out["frame_size"] = frame_size
    out["window_duration_sec"] = window_duration_sec

    if not isinstance(out["frames"], list):
        raise PitchTrackDataError("frames must be a list")

    frames: list[dict[str, Any]] = []
    for i, raw in enumerate(out["frames"]):
        if not isinstance(raw, Mapping):
            raise PitchTrackDataError(f"frames[{i}] must be a mapping")
        frame = dict(raw)
        for req in ("time_sec", "frequency_hz", "pitch_midi", "pitch", "voiced"):
            if req not in frame:
                raise PitchTrackDataError(f"frames[{i}] missing field: {req}")
        try:
            time_sec = float(frame["time_sec"])
            pitch_midi = float(frame["pitch_midi"])
            voiced = bool(frame["voiced"])
        except (TypeError, ValueError) as exc:
            raise PitchTrackDataError(f"frames[{i}] has invalid fields") from exc

        hz_raw = frame["frequency_hz"]
        if hz_raw is None:
            frequency_hz = None
        else:
            try:
                frequency_hz = float(hz_raw)
            except (TypeError, ValueError) as exc:
                raise PitchTrackDataError(f"frames[{i}].frequency_hz invalid") from exc

        pitch = frame["pitch"]
        if pitch is not None:
            pitch = str(pitch)

        frames.append(
            {
                "time_sec": time_sec,
                "frequency_hz": frequency_hz,
                "pitch_midi": pitch_midi,
                "pitch": pitch,
                "voiced": voiced,
            }
        )
    out["frames"] = frames
    return out


def dump_pitch_track_data(data: Mapping[str, Any], path: str | Path, *, indent: int = 2) -> Path:
    validated = validate_pitch_track_data(data)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(validated, ensure_ascii=False, indent=indent), encoding="utf-8")
    return target


def load_pitch_track_data(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_pitch_track_data(payload)
