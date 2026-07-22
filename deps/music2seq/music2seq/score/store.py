"""Persistence helpers for score note events."""

from __future__ import annotations

import json
from pathlib import Path

from music2seq.types import NoteEvent


def save_note_events(path: str | Path, events: list[NoteEvent]) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps([event.to_dict() for event in events], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out


def load_note_events(path: str | Path) -> list[NoteEvent]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [NoteEvent.from_dict(item) for item in data]
