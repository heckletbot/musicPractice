"""Load Score from MusicXML with interval division."""

from __future__ import annotations

from pathlib import Path
import uuid

from music_practice.models import Score
from music_practice.score.intervals import assign_interval_ids, build_intervals, count_notes_per_interval
from music_practice.score.parser import parse_musicxml


def load_score_from_musicxml(
    musicxml_path: str | Path,
    *,
    interval_measures: int = 4,
    default_tempo_bpm: float = 120.0,
    part_id: str | None = None,
    score_id: str | None = None,
) -> Score:
    path = Path(musicxml_path)
    if not path.exists():
        raise FileNotFoundError(f"MusicXML not found: {path}")

    notes, meta = parse_musicxml(
        path,
        default_tempo_bpm=default_tempo_bpm,
        part_id=part_id,
    )
    assign_interval_ids(notes, interval_measures)
    intervals = build_intervals(meta.total_measures, interval_measures)
    count_notes_per_interval(notes, intervals)

    return Score(
        score_id=score_id or f"sc_{uuid.uuid4().hex[:8]}",
        title=meta.title,
        tempo=meta.tempo,
        time_signature=meta.time_signature,
        key=meta.key,
        total_measures=meta.total_measures,
        intervals=intervals,
        notes=notes,
        source_path=str(path.resolve()),
    )
