"""Align parsed score note times to template audio timeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from music2seq.types import NoteEvent


@dataclass(frozen=True)
class ScoreCalibration:
    template_duration_sec: float
    score_end_sec: float
    scale: float
    offset_sec: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calibrate_note_events_to_template(
    events: list[NoteEvent],
    template_duration_sec: float,
    *,
    offset_sec: float = 0.0,
) -> tuple[list[NoteEvent], ScoreCalibration]:
    """Linearly map score-relative seconds onto the template audio axis.

    Parsed MusicXML times assume nominal tempo; Sibelius-exported template audio
    may differ slightly in total length. We stretch ``[0, score_end]`` to fit
    ``[offset, template_duration]``.
    """

    if not events:
        cal = ScoreCalibration(
            template_duration_sec=template_duration_sec,
            score_end_sec=0.0,
            scale=1.0,
            offset_sec=offset_sec,
        )
        return [], cal

    score_end = max(event.end_sec for event in events)
    usable_template = max(template_duration_sec - offset_sec, 1e-6)
    scale = usable_template / score_end if score_end > 0 else 1.0

    calibrated: list[NoteEvent] = []
    for event in events:
        start_sec = offset_sec + event.start_sec * scale
        end_sec = offset_sec + event.end_sec * scale
        calibrated.append(
            NoteEvent(
                note_id=event.note_id,
                measure=event.measure,
                beat=event.beat,
                pitch_midi=event.pitch_midi,
                start_sec=float(start_sec),
                end_sec=float(end_sec),
                duration_sec=float(end_sec - start_sec),
                part_id=event.part_id,
                voice=event.voice,
            )
        )

    cal = ScoreCalibration(
        template_duration_sec=template_duration_sec,
        score_end_sec=float(score_end),
        scale=float(scale),
        offset_sec=float(offset_sec),
    )
    return calibrated, cal
