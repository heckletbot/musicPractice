"""MusicXML → ScoreData converter (no recognition dependency)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from music_practice.contract.bridge import score_to_score_data
from music_practice.score.import_score import make_score_id
from music_practice.score.loader import load_score_from_musicxml
from music_practice.score.store import _sha256_file, _utc_now


def convert_musicxml(
    musicxml_path: str | Path,
    *,
    score_id: str | None = None,
    interval_measures: int = 4,
    default_tempo_bpm: float = 120.0,
    part_id: str | None = None,
) -> dict[str, Any]:
    """Parse MusicXML and return fixed-interface ``ScoreData`` (no persist, no recognize)."""
    path = Path(musicxml_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"MusicXML not found: {path}")
    resolved_id = make_score_id(path, explicit=score_id)
    score = load_score_from_musicxml(
        path,
        interval_measures=interval_measures,
        default_tempo_bpm=default_tempo_bpm,
        part_id=part_id,
        score_id=resolved_id,
    )
    score.source_path = str(path)
    score.source_sha256 = _sha256_file(path)
    score.created_at = _utc_now()
    score.interval_measures = interval_measures
    return score_to_score_data(score)
