"""Domain models for music-practice."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from music_practice.types import ScoreSummaryDict


@dataclass
class ParsedNote:
    pitch: str
    measure: int
    beat: float
    onset: float
    duration: float
    interval_id: int
    pitch_midi: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "pitch": self.pitch,
            "measure": self.measure,
            "beat": self.beat,
            "onset": self.onset,
            "duration": self.duration,
            "interval_id": self.interval_id,
        }
        if self.pitch_midi is not None:
            data["pitch_midi"] = self.pitch_midi
        return data


@dataclass
class Interval:
    id: int
    start_measure: int
    end_measure: int
    note_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "start_measure": self.start_measure,
            "end_measure": self.end_measure,
            "note_count": self.note_count,
        }


@dataclass
class Score:
    score_id: str
    title: str
    tempo: float
    time_signature: str
    key: str
    total_measures: int
    intervals: list[Interval] = field(default_factory=list)
    notes: list[ParsedNote] = field(default_factory=list)
    source_path: str | None = None
    source_sha256: str | None = None
    created_at: str | None = None
    interval_measures: int = 4

    @property
    def interval_count(self) -> int:
        return len(self.intervals)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score_id": self.score_id,
            "title": self.title,
            "tempo": self.tempo,
            "time_signature": self.time_signature,
            "key": self.key,
            "total_measures": self.total_measures,
            "interval_measures": self.interval_measures,
            "interval_count": self.interval_count,
            "intervals": [item.to_dict() for item in self.intervals],
            "note_count": len(self.notes),
            "notes": [item.to_dict() for item in self.notes],
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "created_at": self.created_at,
        }

    def to_summary(self) -> ScoreSummaryDict:
        return {
            "score_id": self.score_id,
            "title": self.title,
            "tempo": self.tempo,
            "time_signature": self.time_signature,
            "key": self.key,
            "total_measures": self.total_measures,
            "interval_count": self.interval_count,
            "note_count": len(self.notes),
        }
