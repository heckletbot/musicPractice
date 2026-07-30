"""Bridge between internal models and fixed ScoreData / PitchTrackData contracts."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any, Mapping

from music_practice.contract.schema import (
    PITCH_TRACK_DATA_SCHEMA,
    PITCH_TRACK_DATA_VERSION,
    SCORE_DATA_SCHEMA,
    SCORE_DATA_VERSION,
)
from music_practice.contract.validate import validate_pitch_track_data, validate_score_data
from music_practice.models import Interval, ParsedNote, Score

if TYPE_CHECKING:
    from music_practice.pitch.detector import PitchTrack


def score_to_score_data(score: Score) -> dict[str, Any]:
    """Convert an in-memory ``Score`` into validated ScoreData."""
    by_measure: dict[int, int] = defaultdict(int)
    notes: list[dict[str, Any]] = []
    for note in score.notes:
        by_measure[note.measure] += 1
        notes.append(
            {
                "pitch": note.pitch,
                "pitch_midi": note.pitch_midi,
                "measure": note.measure,
                "note_index_in_measure": by_measure[note.measure],
                "beat": note.beat,
                "onset": note.onset,
                "duration": note.duration,
                "interval_id": note.interval_id,
                "is_rest": False,
            }
        )

    payload: dict[str, Any] = {
        "schema": SCORE_DATA_SCHEMA,
        "schema_version": SCORE_DATA_VERSION,
        "score_id": score.score_id,
        "title": score.title,
        "tempo": float(score.tempo),
        "time_signature": score.time_signature,
        "key": score.key,
        "total_measures": int(score.total_measures),
        "interval_measures": int(score.interval_measures),
        "intervals": [item.to_dict() for item in score.intervals],
        "notes": notes,
    }
    if score.source_path is not None:
        payload["source_path"] = score.source_path
    if score.source_sha256 is not None:
        payload["source_sha256"] = score.source_sha256
    if score.created_at is not None:
        payload["created_at"] = score.created_at
    return validate_score_data(payload)


def score_data_to_score(data: Mapping[str, Any]) -> Score:
    """Build an internal ``Score`` from ScoreData (for modules that still take Score)."""
    validated = validate_score_data(data)
    notes = [
        ParsedNote(
            pitch=item["pitch"],
            measure=int(item["measure"]),
            beat=float(item["beat"]),
            onset=float(item["onset"]),
            duration=float(item["duration"]),
            interval_id=int(item["interval_id"]),
            pitch_midi=None if item.get("pitch_midi") is None else int(round(float(item["pitch_midi"]))),
        )
        for item in validated["notes"]
        if not item.get("is_rest")
    ]
    intervals = [Interval(**item) for item in validated["intervals"]]
    return Score(
        score_id=str(validated["score_id"]),
        title=str(validated["title"]),
        tempo=float(validated["tempo"]),
        time_signature=str(validated["time_signature"]),
        key=str(validated["key"]),
        total_measures=int(validated["total_measures"]),
        intervals=intervals,
        notes=notes,
        source_path=validated.get("source_path"),
        source_sha256=validated.get("source_sha256"),
        created_at=validated.get("created_at"),
        interval_measures=int(validated["interval_measures"]),
    )


def find_start_index(score_data: Mapping[str, Any], start_from: Mapping[str, Any] | None) -> int:
    """Resolve start_from → index into score_data['notes']."""
    notes = list(score_data["notes"])
    if not notes:
        raise ValueError("score_data.notes is empty")
    if start_from is None:
        return 0
    if "measure" not in start_from:
        raise ValueError("start_from.measure is required")
    # Accept both note_index and note_index_in_measure
    if "note_index" in start_from:
        note_index = int(start_from["note_index"])
    elif "note_index_in_measure" in start_from:
        note_index = int(start_from["note_index_in_measure"])
    else:
        raise ValueError("start_from.note_index is required")
    measure = int(start_from["measure"])
    if note_index < 1:
        raise ValueError("start_from.note_index must be >= 1")
    for i, note in enumerate(notes):
        if int(note["measure"]) == measure and int(note["note_index_in_measure"]) == note_index:
            return i
    raise ValueError(f"start_from not found: measure={measure} note_index={note_index}")


def slice_practice_notes(
    score_data: Mapping[str, Any],
    start_from: Mapping[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Return notes from start_from onward with onsets rebased to 0, plus resolved start_from."""
    validated = validate_score_data(score_data)
    idx = find_start_index(validated, start_from)
    origin = float(validated["notes"][idx]["onset"])
    sliced: list[dict[str, Any]] = []
    for note in validated["notes"][idx:]:
        item = dict(note)
        item["onset"] = float(note["onset"]) - origin
        sliced.append(item)
    resolved = {
        "measure": int(validated["notes"][idx]["measure"]),
        "note_index": int(validated["notes"][idx]["note_index_in_measure"]),
    }
    return sliced, resolved


def pitch_track_to_pitch_track_data(track: PitchTrack) -> dict[str, Any]:
    """Convert an in-memory ``PitchTrack`` into validated PitchTrackData.

    Imports ``PitchTrack`` only when called so ``music_practice.contract`` stays
    free of audio-stack imports at module load time.
    """
    payload = {
        "schema": PITCH_TRACK_DATA_SCHEMA,
        "schema_version": PITCH_TRACK_DATA_VERSION,
        **track.to_dict(),
    }
    return validate_pitch_track_data(payload)


def pitch_track_data_to_pitch_track(data: Mapping[str, Any]) -> PitchTrack:
    """Build an internal ``PitchTrack`` from PitchTrackData."""
    # Lazy import: avoid pulling librosa when only ScoreData tools are used.
    from music_practice.pitch.detector import PitchFrame, PitchTrack as PitchTrackCls

    validated = validate_pitch_track_data(data)
    frames = [
        PitchFrame(
            time_sec=float(item["time_sec"]),
            frequency_hz=None if item["frequency_hz"] is None else float(item["frequency_hz"]),
            pitch_midi=float(item["pitch_midi"]),
            pitch=None if item["pitch"] is None else str(item["pitch"]),
            voiced=bool(item["voiced"]),
        )
        for item in validated["frames"]
    ]
    return PitchTrackCls(
        sample_rate=int(validated["sample_rate"]),
        frame_size=int(validated["frame_size"]),
        window_duration_sec=float(validated["window_duration_sec"]),
        frames=frames,
    )


def coerce_pitch_track(track: PitchTrack | Mapping[str, Any]) -> PitchTrack:
    """Accept PitchTrack or PitchTrackData mapping; return internal PitchTrack."""
    from music_practice.pitch.detector import PitchTrack as PitchTrackCls

    if isinstance(track, PitchTrackCls):
        return track
    if isinstance(track, Mapping):
        return pitch_track_data_to_pitch_track(track)
    raise TypeError("track must be PitchTrack or PitchTrackData mapping")
