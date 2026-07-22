"""Resolve score note references."""

from __future__ import annotations

from music_practice.models import ParsedNote, Score
from music_practice.types import StartNoteRef


def notes_in_measure(score: Score, measure: int) -> list[ParsedNote]:
    items = [note for note in score.notes if note.measure == measure]
    items.sort(key=lambda note: (note.beat, note.onset))
    return items


def resolve_start_note(score: Score, ref: StartNoteRef) -> ParsedNote:
    items = notes_in_measure(score, ref.measure)
    if ref.note_index_in_measure < 1:
        raise ValueError("note_index_in_measure must be >= 1")
    if ref.note_index_in_measure > len(items):
        raise ValueError(
            f"measure {ref.measure} has {len(items)} playable notes, "
            f"requested index {ref.note_index_in_measure}"
        )
    return items[ref.note_index_in_measure - 1]
