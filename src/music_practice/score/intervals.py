"""Interval division for practice sections."""

from __future__ import annotations

from music_practice.models import Interval, ParsedNote


def build_intervals(total_measures: int, measures_per_interval: int = 4) -> list[Interval]:
    if total_measures <= 0:
        return []
    if measures_per_interval <= 0:
        raise ValueError("measures_per_interval must be positive")

    intervals: list[Interval] = []
    interval_id = 0
    start = 1
    while start <= total_measures:
        end = min(start + measures_per_interval - 1, total_measures)
        intervals.append(Interval(id=interval_id, start_measure=start, end_measure=end))
        interval_id += 1
        start = end + 1
    return intervals


def interval_id_for_measure(measure: int, measures_per_interval: int) -> int:
    if measure <= 0:
        raise ValueError("measure must be positive")
    return (measure - 1) // measures_per_interval


def assign_interval_ids(notes: list[ParsedNote], measures_per_interval: int) -> None:
    for note in notes:
        note.interval_id = interval_id_for_measure(note.measure, measures_per_interval)


def count_notes_per_interval(notes: list[ParsedNote], intervals: list[Interval]) -> None:
    counts = {item.id: 0 for item in intervals}
    for note in notes:
        counts[note.interval_id] = counts.get(note.interval_id, 0) + 1
    for item in intervals:
        item.note_count = counts.get(item.id, 0)
