"""Persist parsed score data to disk."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from music_practice.models import Interval, ParsedNote, Score
from music_practice.types import ScoreListItemDict

SCHEMA_VERSION = "1.0"


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_scores_dir() -> Path:
    return project_root() / "data" / "scores"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def score_dir(score_id: str, scores_dir: Path | None = None) -> Path:
    return (scores_dir or default_scores_dir()) / score_id


def save_score(
    score: Score,
    *,
    scores_dir: Path | None = None,
    interval_measures: int = 4,
    overwrite: bool = False,
) -> Path:
    root = score_dir(score.score_id, scores_dir)
    if root.exists() and not overwrite:
        raise FileExistsError(f"Score already exists: {score.score_id} ({root})")
    root.mkdir(parents=True, exist_ok=True)

    meta = {
        "schema_version": SCHEMA_VERSION,
        "score_id": score.score_id,
        "title": score.title,
        "tempo": score.tempo,
        "time_signature": score.time_signature,
        "key": score.key,
        "total_measures": score.total_measures,
        "interval_measures": interval_measures,
        "interval_count": score.interval_count,
        "intervals": [item.to_dict() for item in score.intervals],
        "source_path": score.source_path,
        "source_sha256": score.source_sha256,
        "created_at": score.created_at or _utc_now(),
        "note_count": len(score.notes),
    }
    notes = {
        "schema_version": SCHEMA_VERSION,
        "score_id": score.score_id,
        "notes": [_note_to_dict(note) for note in score.notes],
    }

    (root / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "notes.json").write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")
    return root


def load_score(score_id: str, *, scores_dir: Path | None = None) -> Score:
    root = score_dir(score_id, scores_dir)
    meta_path = root / "meta.json"
    notes_path = root / "notes.json"
    if not meta_path.exists() or not notes_path.exists():
        raise FileNotFoundError(f"Score not found: {score_id} ({root})")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    notes_payload = json.loads(notes_path.read_text(encoding="utf-8"))
    intervals = [Interval(**item) for item in meta.get("intervals", [])]
    notes = [_note_from_dict(item) for item in notes_payload.get("notes", [])]

    return Score(
        score_id=meta["score_id"],
        title=meta["title"],
        tempo=float(meta["tempo"]),
        time_signature=meta["time_signature"],
        key=meta["key"],
        total_measures=int(meta["total_measures"]),
        intervals=intervals,
        notes=notes,
        source_path=meta.get("source_path"),
        source_sha256=meta.get("source_sha256"),
        created_at=meta.get("created_at"),
        interval_measures=int(meta.get("interval_measures", 4)),
    )


def list_scores(*, scores_dir: Path | None = None) -> list[ScoreListItemDict]:
    base = scores_dir or default_scores_dir()
    if not base.exists():
        return []
    items: list[dict] = []
    for entry in sorted(base.iterdir()):
        if not entry.is_dir():
            continue
        meta_path = entry / "meta.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        items.append(
            {
                "score_id": meta.get("score_id", entry.name),
                "title": meta.get("title"),
                "total_measures": meta.get("total_measures"),
                "interval_count": meta.get("interval_count"),
                "note_count": meta.get("note_count"),
                "created_at": meta.get("created_at"),
            }
        )
    return items


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _note_to_dict(note: ParsedNote) -> dict:
    data = note.to_dict()
    if note.pitch_midi is not None:
        data["pitch_midi"] = note.pitch_midi
    return data


def _note_from_dict(data: dict) -> ParsedNote:
    return ParsedNote(
        pitch=data["pitch"],
        measure=int(data["measure"]),
        beat=float(data["beat"]),
        onset=float(data["onset"]),
        duration=float(data["duration"]),
        interval_id=int(data["interval_id"]),
        pitch_midi=data.get("pitch_midi"),
    )
