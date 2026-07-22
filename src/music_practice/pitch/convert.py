"""Hz / MIDI / note name conversion (OnsetDectection PitchEvaluator + PitchNameCalculator)."""

from __future__ import annotations

import math

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def hz_to_midi(hz: float, *, a4_hz: float = 442.0) -> float:
    if hz <= 0:
        return -1.0
    return 69.0 + 12.0 * math.log2(hz / a4_hz)


def midi_to_hz(midi: float, *, a4_hz: float = 442.0) -> float:
    if midi < 0:
        return 0.0
    return a4_hz * (2.0 ** ((midi - 69.0) / 12.0))


def hz_to_pitch_name(hz: float, *, a4_hz: float = 442.0) -> str | None:
    if hz <= 0:
        return None
    note_number = int(round(hz_to_midi(hz, a4_hz=a4_hz)))
    octave = note_number // 12 - 1
    name = NOTE_NAMES[note_number % 12]
    return f"{name}{octave}"
