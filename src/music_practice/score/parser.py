"""MusicXML parser for single-part scores."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET

from music_practice.models import ParsedNote

STEP_TO_SEMITONE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

FIFTHS_TO_KEY = {
    -7: "Cb major",
    -6: "Gb major",
    -5: "Db major",
    -4: "Ab major",
    -3: "Eb major",
    -2: "Bb major",
    -1: "F major",
    0: "C major",
    1: "G major",
    2: "D major",
    3: "A major",
    4: "E major",
    5: "B major",
    6: "F# major",
    7: "C# major",
}


@dataclass
class ParseContext:
    """Parsing state: divisions, tempo, time signature, transpose, cursor."""

    divisions: float = 1.0
    tempo_bpm: float = 120.0
    beats: int = 4
    beat_type: int = 4
    chromatic: int = 0
    diatonic: int = 0
    current_time: float = 0.0

    @property
    def time_per_division(self) -> float:
        return 60.0 / self.tempo_bpm


def _strip_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _children(node: ET.Element, tag: str) -> list[ET.Element]:
    return [child for child in list(node) if _strip_namespace(child.tag) == tag]


def _child(node: ET.Element, tag: str) -> ET.Element | None:
    matches = _children(node, tag)
    return matches[0] if matches else None


def _text(node: ET.Element, tag: str, default: str | None = None) -> str | None:
    child = _child(node, tag)
    if child is None or child.text is None:
        return default
    return child.text.strip()


def _iter_parts(root: ET.Element) -> list[ET.Element]:
    return [node for node in root.iter() if _strip_namespace(node.tag) == "part"]


def _work_title(root: ET.Element) -> str | None:
    for path in (("work", "work-title"), ("movement-title",)):
        if len(path) == 2:
            work = _child(root, path[0])
            if work is not None:
                title = _text(work, path[1])
                if title:
                    return title
        else:
            title = _text(root, path[0])
            if title:
                return title
    return None


def _tempo_from_direction(direction: ET.Element) -> float | None:
    """Return tempo as quarter-notes-per-minute (MusicXML sound tempo unit)."""
    sound = _child(direction, "sound")
    if sound is not None and sound.attrib.get("tempo") is not None:
        # sound/@tempo is defined as quarter notes per minute.
        return float(sound.attrib["tempo"])
    metronome = next(
        (node for node in direction.iter() if _strip_namespace(node.tag) == "metronome"),
        None,
    )
    if metronome is None:
        return None
    per_minute = _text(metronome, "per-minute")
    if per_minute is None:
        return None
    return _metronome_to_quarter_bpm(metronome, float(per_minute))


# MusicXML beat-unit -> length in quarter notes (before dots).
_BEAT_UNIT_QUARTERS: dict[str, float] = {
    "maxima": 32.0,
    "long": 16.0,
    "breve": 8.0,
    "whole": 4.0,
    "half": 2.0,
    "quarter": 1.0,
    "eighth": 0.5,
    "16th": 0.25,
    "32nd": 0.125,
    "64th": 0.0625,
    "128th": 0.03125,
    "256th": 0.015625,
    "512th": 0.0078125,
    "1024th": 0.00390625,
}


def _metronome_to_quarter_bpm(metronome: ET.Element, per_minute: float) -> float:
    """Convert visual metronome (beat-unit[+dot*] = N) to quarter-note BPM."""
    unit = (_text(metronome, "beat-unit") or "quarter").strip().lower()
    quarters = _BEAT_UNIT_QUARTERS.get(unit, 1.0)
    # Each beat-unit-dot multiplies duration by 3/2 (single / double / ... dots).
    dots = sum(1 for node in list(metronome) if _strip_namespace(node.tag) == "beat-unit-dot")
    if dots:
        quarters *= (1.5**dots)
    # N metronome-beats/min * quarters/metronome-beat = quarters/min.
    return float(per_minute) * float(quarters)


def _apply_attributes(attributes: ET.Element, ctx: ParseContext) -> None:
    """Apply measure-level attributes (time signature, divisions, transpose, multiple-rest)."""
    time_elem = _child(attributes, "time")
    if time_elem is not None:
        beats = _text(time_elem, "beats")
        beat_type = _text(time_elem, "beat-type")
        if beats is not None:
            ctx.beats = int(beats)
        if beat_type is not None:
            ctx.beat_type = int(beat_type)

    divisions = _text(attributes, "divisions")
    if divisions is not None:
        ctx.divisions = max(float(divisions), 1.0)

    transpose = _child(attributes, "transpose")
    if transpose is not None:
        diatonic = _text(transpose, "diatonic")
        chromatic = _text(transpose, "chromatic")
        if diatonic is not None:
            ctx.diatonic = int(diatonic)
        if chromatic is not None:
            ctx.chromatic = int(chromatic)

    measure_style = _child(attributes, "measure-style")
    if measure_style is not None:
        multiple_rest = _text(measure_style, "multiple-rest")
        if multiple_rest is not None:
            rest_measures = int(multiple_rest)
            measure_duration = rest_measures * ctx.beats * ctx.time_per_division
            ctx.current_time += measure_duration


def _key_from_fifths(fifths: int) -> str:
    return FIFTHS_TO_KEY.get(fifths, f"{fifths} fifths")


def _pitch_name(step: str, alter: int, octave: int) -> str:
    suffix = ""
    if alter == 1:
        suffix = "#"
    elif alter == 2:
        suffix = "##"
    elif alter == -1:
        suffix = "b"
    elif alter == -2:
        suffix = "bb"
    return f"{step}{suffix}{octave}"


def _pitch_midi(step: str, alter: int, octave: int, chromatic: int) -> int:
    """Convert note name to MIDI."""
    base = STEP_TO_SEMITONE[step.upper()]
    return (octave + 1) * 12 + base + alter + chromatic


def _note_duration_sec(duration_ticks: float, ctx: ParseContext) -> float:
    return duration_ticks / ctx.divisions * ctx.time_per_division


def _parse_pitch(note_elem: ET.Element, ctx: ParseContext) -> tuple[str, int] | None:
    pitch = _child(note_elem, "pitch")
    if pitch is None:
        return None
    step = _text(pitch, "step")
    octave_text = _text(pitch, "octave")
    if step not in STEP_TO_SEMITONE or octave_text is None:
        return None
    alter = int(float(_text(pitch, "alter", "0") or "0"))
    octave = int(octave_text)
    name = _pitch_name(step, alter, octave)
    midi = _pitch_midi(step, alter, octave, ctx.chromatic)
    return name, midi


def _is_rest(note_elem: ET.Element) -> bool:
    return _child(note_elem, "rest") is not None


def _is_grace(note_elem: ET.Element) -> bool:
    return _child(note_elem, "grace") is not None


def _handle_note(
    note_elem: ET.Element,
    ctx: ParseContext,
    *,
    measure_no: int,
    measure_start_div: float,
    current_div: float,
) -> tuple[ParsedNote | None, float]:
    """Handle rest, grace, and normal notes."""
    dur_div = float(_text(note_elem, "duration", "0") or "0")
    is_chord = _child(note_elem, "chord") is not None

    if _is_grace(note_elem):
        return None, current_div

    if _is_rest(note_elem):
        duration = _note_duration_sec(dur_div, ctx)
        ctx.current_time += duration
        if not is_chord:
            return None, current_div + dur_div
        return None, current_div

    pitch_info = _parse_pitch(note_elem, ctx)
    if pitch_info is None or dur_div <= 0:
        if not is_chord:
            return None, current_div + dur_div
        return None, current_div

    pitch_name, pitch_midi = pitch_info
    duration = _note_duration_sec(dur_div, ctx)
    offset = ctx.current_time
    beat = (current_div - measure_start_div) / ctx.divisions + 1.0

    note = ParsedNote(
        pitch=pitch_name,
        measure=measure_no,
        beat=float(beat),
        onset=float(offset),
        duration=float(duration),
        interval_id=0,
        pitch_midi=pitch_midi,
    )

    ctx.current_time += duration
    next_div = current_div if is_chord else current_div + dur_div
    return note, next_div


@dataclass
class ParsedScoreMeta:
    title: str
    tempo: float
    time_signature: str
    key: str
    total_measures: int


def parse_musicxml(
    path: str | Path,
    *,
    default_tempo_bpm: float = 120.0,
    part_id: str | None = None,
    session_start_measure: int | None = None,
) -> tuple[list[ParsedNote], ParsedScoreMeta]:
    """Parse MusicXML into notes with absolute onset (seconds from score start).

    If session_start_measure is set, note.onset is rebased to 0 at that measure's first beat.
    """
    xml_path = Path(path)
    root = ET.parse(xml_path).getroot()

    title = _work_title(root) or xml_path.stem
    ctx = ParseContext(tempo_bpm=default_tempo_bpm)
    key_fifths = 0
    notes: list[ParsedNote] = []
    max_measure = 0

    parts = _iter_parts(root)
    if part_id is not None:
        parts = [part for part in parts if part.attrib.get("id") == part_id]
    elif parts:
        parts = [parts[0]]

    for part in parts:
        current_div = 0.0

        for measure in _children(part, "measure"):
            measure_no_text = measure.attrib.get("number", "0").split(".")[0]
            measure_no = int(measure_no_text or "0")
            max_measure = max(max_measure, measure_no)
            measure_start_div = current_div

            for item in list(measure):
                tag = _strip_namespace(item.tag)
                if tag == "attributes":
                    key_elem = _child(item, "key")
                    if key_elem is not None:
                        fifths_text = _text(key_elem, "fifths")
                        if fifths_text is not None:
                            key_fifths = int(fifths_text)
                    _apply_attributes(item, ctx)
                    continue
                if tag == "direction":
                    tempo = _tempo_from_direction(item)
                    if tempo is not None:
                        ctx.tempo_bpm = tempo
                    continue
                if tag == "backup":
                    current_div -= float(_text(item, "duration", "0") or "0")
                    continue
                if tag == "forward":
                    current_div += float(_text(item, "duration", "0") or "0")
                    continue
                if tag != "note":
                    continue

                note, current_div = _handle_note(
                    item,
                    ctx,
                    measure_no=measure_no,
                    measure_start_div=measure_start_div,
                    current_div=current_div,
                )
                if note is not None:
                    notes.append(note)

    if session_start_measure is not None:
        anchor = _onset_at_measure(notes, session_start_measure)
        for note in notes:
            if note.measure >= session_start_measure:
                note.onset -= anchor

    meta = ParsedScoreMeta(
        title=title,
        tempo=ctx.tempo_bpm,
        time_signature=f"{ctx.beats}/{ctx.beat_type}",
        key=_key_from_fifths(key_fifths),
        total_measures=max_measure,
    )
    notes.sort(key=lambda item: (item.onset, item.measure, item.beat))
    return notes, meta


def _onset_at_measure(notes: list[ParsedNote], measure: int) -> float:
    for note in notes:
        if note.measure == measure:
            return note.onset
    for note in notes:
        if note.measure >= measure:
            return note.onset
    return 0.0
