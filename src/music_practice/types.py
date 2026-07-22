"""Shared typed views for API results and inspection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict


class JsonDict(TypedDict, total=False):
    """Generic JSON-serializable mapping returned by ``to_dict()`` helpers."""


class ScoreSummaryDict(TypedDict):
    score_id: str
    title: str
    tempo: float
    time_signature: str
    key: str
    total_measures: int
    interval_count: int
    note_count: int


class ScoreListItemDict(TypedDict, total=False):
    score_id: str
    title: str | None
    total_measures: int | None
    interval_count: int | None
    note_count: int | None
    created_at: str | None


class ObservationDict(TypedDict):
    kind: str
    data: dict[str, Any]


@dataclass(frozen=True)
class StartNoteRef:
    measure: int
    note_index_in_measure: int

    def to_dict(self) -> dict[str, int]:
        return {
            "measure": self.measure,
            "note_index_in_measure": self.note_index_in_measure,
        }
