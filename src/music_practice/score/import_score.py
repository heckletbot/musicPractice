"""Import MusicXML from external path and persist score data."""

from __future__ import annotations

from pathlib import Path
import re
import uuid

from music_practice.models import Score
from music_practice.score.loader import load_score_from_musicxml
from music_practice.score.store import _sha256_file, _utc_now, default_scores_dir, save_score


def _slugify(text: str) -> str:
    slug = re.sub(r"[^\w\-]+", "_", text.strip(), flags=re.UNICODE)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:48] or "score"


def make_score_id(musicxml_path: Path, *, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    stem = _slugify(musicxml_path.stem)
    return f"{stem}_{uuid.uuid4().hex[:8]}"


def import_musicxml(
    musicxml_path: str | Path,
    *,
    scores_dir: Path | None = None,
    interval_measures: int = 4,
    default_tempo_bpm: float = 120.0,
    part_id: str | None = None,
    score_id: str | None = None,
    overwrite: bool = False,
) -> Score:
    """Parse MusicXML, build Score, and persist under data/scores/{score_id}/."""
    path = Path(musicxml_path).resolve()
    resolved_score_id = make_score_id(path, explicit=score_id)

    score = load_score_from_musicxml(
        path,
        interval_measures=interval_measures,
        default_tempo_bpm=default_tempo_bpm,
        part_id=part_id,
        score_id=resolved_score_id,
    )
    score.source_sha256 = _sha256_file(path)
    score.created_at = _utc_now()
    score.interval_measures = interval_measures

    save_score(
        score,
        scores_dir=scores_dir or default_scores_dir(),
        interval_measures=interval_measures,
        overwrite=overwrite,
    )
    return score
