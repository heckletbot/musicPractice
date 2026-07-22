"""Configuration and result types for start-point detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from music_practice.types import StartNoteRef


@dataclass(frozen=True)
class StartDetectContext:
    """Start-detect parameters.

    Streaming path concatenates PCM frames, then runs DTW on the trailing
    ``max_query_sec`` window. Empirically on the 30-case fixture:

    - 0.3~1.0s window: unstable (~33–67% depending on slice mode)
    - 1.5s: ~93% (trailing)
    - 2.0s: 100% (trailing)  ← default

    ``dtw_interval_sec`` is how often DTW is polled (wall clock), not the PCM window.
    """

    window_after_sec: float = 3.0
    wait_timeout_sec: float = 30.0
    score_threshold: float = 0.35
    min_query_sec: float = 1.0
    max_query_sec: float = 2.0
    dtw_interval_sec: float = 0.3
    anchor_tolerance_sec: float = 1.0

    def __post_init__(self) -> None:
        if self.min_query_sec > self.max_query_sec:
            raise ValueError(
                f"min_query_sec ({self.min_query_sec}) > max_query_sec ({self.max_query_sec})"
            )


@dataclass
class DetectedNote:
    measure: int
    beat: float
    note_index_in_measure: int
    pitch: str | None
    pitch_midi: int | None
    onset: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "measure": self.measure,
            "beat": self.beat,
            "note_index_in_measure": self.note_index_in_measure,
            "pitch": self.pitch,
            "pitch_midi": self.pitch_midi,
            "onset": self.onset,
        }


@dataclass
class StartDetectResult:
    start_note: StartNoteRef
    started: bool
    timed_out: bool = False
    wait_elapsed_sec: float | None = None
    wait_timeout_sec: float = 30.0
    detected_note: DetectedNote | None = None
    confidence: float = 0.0
    template_sec: float | None = None
    detected_template_sec: float | None = None
    query_duration_sec: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_note": self.start_note.to_dict(),
            "started": self.started,
            "timed_out": self.timed_out,
            "wait_elapsed_sec": self.wait_elapsed_sec,
            "wait_timeout_sec": self.wait_timeout_sec,
            "detected_note": self.detected_note.to_dict() if self.detected_note else None,
            "confidence": self.confidence,
            "template_sec": self.template_sec,
            "detected_template_sec": self.detected_template_sec,
            "query_duration_sec": self.query_duration_sec,
            "extra": self.extra,
        }
