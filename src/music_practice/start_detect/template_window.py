"""Template pitch window slicing and anchor resolution."""

from __future__ import annotations

import numpy as np

from music_practice.start_match.features.pitch_extractor import PitchSequence
from music_practice.start_match.score.store import load_note_events
from music_practice.start_match.template.store import TemplatePackage
from music_practice.start_match.types import NoteEvent

from music_practice.types import StartNoteRef


def note_events_in_measure(events: list[NoteEvent], measure: int) -> list[NoteEvent]:
    items = [event for event in events if event.measure == measure]
    items.sort(key=lambda event: (event.beat, event.start_sec))
    return items


def resolve_template_sec(events: list[NoteEvent], ref: StartNoteRef) -> float:
    items = note_events_in_measure(events, ref.measure)
    if ref.note_index_in_measure < 1 or ref.note_index_in_measure > len(items):
        raise ValueError(
            f"measure {ref.measure} 有 {len(items)} 个 note_event，"
            f"请求 index {ref.note_index_in_measure}"
        )
    return float(items[ref.note_index_in_measure - 1].start_sec)


def resolve_template_sec_from_package(package: TemplatePackage, ref: StartNoteRef) -> float:
    if not package.note_events:
        raise ValueError(f"模板 {package.template_id} 缺少 note_events.json")
    return resolve_template_sec(package.note_events, ref)


def slice_pitch_window(
    seq: PitchSequence,
    start_sec: float,
    end_sec: float,
) -> tuple[PitchSequence, int]:
    """Return a pitch sub-sequence and the absolute center frame offset at slice start."""
    start_frame = int(round(start_sec * seq.sample_rate / seq.hop_length))
    end_frame = int(round(end_sec * seq.sample_rate / seq.hop_length))
    centers = seq.center_frames
    mask = (centers >= start_frame) & (centers <= end_frame)
    indices = np.flatnonzero(mask)
    if indices.size == 0:
        raise ValueError("局部搜索窗口内没有可用特征帧")
    lo = int(indices[0])
    hi = int(indices[-1]) + 1
    return (
        PitchSequence(
            features=seq.features[lo:hi],
            center_frames=seq.center_frames[lo:hi] - seq.center_frames[lo],
            sample_rate=seq.sample_rate,
            hop_length=seq.hop_length,
            duration_sec=(seq.center_frames[hi - 1] - seq.center_frames[lo]) * seq.hop_length / seq.sample_rate,
        ),
        int(seq.center_frames[lo]),
    )


def load_package_note_events(package: TemplatePackage) -> list[NoteEvent]:
    if package.note_events:
        return package.note_events
    if package.root is None:
        raise ValueError("模板包缺少 note_events")
    return load_note_events(package.root / "note_events.json")
