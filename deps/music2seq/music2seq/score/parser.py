"""Minimal MusicXML note-event parser."""

from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

from music2seq.types import NoteEvent

STEP_TO_SEMITONE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


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


def _tempo_from_direction(direction: ET.Element) -> float | None:
    sound = _child(direction, "sound")
    if sound is not None and sound.attrib.get("tempo") is not None:
        return float(sound.attrib["tempo"])
    metronome = next((node for node in direction.iter() if _strip_namespace(node.tag) == "metronome"), None)
    if metronome is None:
        return None
    per_minute = _text(metronome, "per-minute")
    return float(per_minute) if per_minute is not None else None


def _pitch_midi(note: ET.Element) -> int | None:
    pitch = _child(note, "pitch")
    if pitch is None:
        return None
    step = _text(pitch, "step")
    octave = _text(pitch, "octave")
    if step not in STEP_TO_SEMITONE or octave is None:
        return None
    alter = int(float(_text(pitch, "alter", "0") or "0"))
    return (int(octave) + 1) * 12 + STEP_TO_SEMITONE[step] + alter


def parse_musicxml(
    path: str | Path,
    *,
    default_tempo_bpm: float = 60.0,
    part_id: str | None = None,
) -> list[NoteEvent]:
    """Parse MusicXML into approximate note events.

    Timing uses an incremental seconds cursor so mid-score tempo changes do not
    rescale earlier music. Rests advance time but are not emitted; chord notes
    share the current cursor. ``<multiple-rest>`` expands full empty bars.
    Pitch is stored as **concert** MIDI when ``<transpose>`` is present.
    """

    root = ET.parse(Path(path)).getroot()
    events: list[NoteEvent] = []

    parts = _iter_parts(root)
    if part_id is not None:
        parts = [part for part in parts if part.attrib.get("id") == part_id]

    for part in parts:
        current_part_id = part.attrib.get("id")
        divisions = 1.0
        tempo_bpm = default_tempo_bpm
        current_div = 0.0
        current_sec = 0.0
        note_index = 0
        # Time signature (defaults 4/4); needed to expand <multiple-rest>.
        beats = 4.0
        beat_type = 4.0
        # Concert pitch = written + chromatic (Bb clarinet typically -2).
        transpose_chromatic = 0
        # After consuming a multi-measure rest of N bars, skip the next N-1
        # empty placeholder measures so duration is not double-counted.
        skip_measures = 0

        def _sec_per_quarter() -> float:
            return 60.0 / max(tempo_bpm, 1e-6)

        def _divs_to_sec(dur_div: float) -> float:
            return (dur_div / divisions) * _sec_per_quarter()

        for measure in _children(part, "measure"):
            if skip_measures > 0:
                skip_measures -= 1
                continue

            measure_no_text = measure.attrib.get("number", "0").split(".")[0]
            measure_no = int(measure_no_text or "0")
            measure_start_div = current_div
            measure_start_sec = current_sec
            multi_rest_bars = 0

            for item in list(measure):
                tag = _strip_namespace(item.tag)
                if tag == "attributes":
                    div_text = _text(item, "divisions")
                    if div_text is not None:
                        divisions = max(float(div_text), 1.0)
                    time_node = _child(item, "time")
                    if time_node is not None:
                        beats_text = _text(time_node, "beats")
                        beat_type_text = _text(time_node, "beat-type")
                        if beats_text is not None:
                            # Support simple "4" (ignore compound "3+2" for now).
                            beats = float(str(beats_text).split("+")[0])
                        if beat_type_text is not None:
                            beat_type = float(beat_type_text)
                    transpose = _child(item, "transpose")
                    if transpose is not None:
                        chromatic = _text(transpose, "chromatic", "0")
                        transpose_chromatic = int(float(chromatic or "0"))
                    style = _child(item, "measure-style")
                    if style is not None:
                        mr = _text(style, "multiple-rest")
                        if mr is not None:
                            multi_rest_bars = max(int(float(mr)), 0)
                    continue
                if tag == "direction":
                    tempo = _tempo_from_direction(item)
                    if tempo is not None:
                        tempo_bpm = tempo
                    continue
                if tag == "backup":
                    dur_div = float(_text(item, "duration", "0") or "0")
                    current_div -= dur_div
                    current_sec -= _divs_to_sec(dur_div)
                    continue
                if tag == "forward":
                    dur_div = float(_text(item, "duration", "0") or "0")
                    current_div += dur_div
                    current_sec += _divs_to_sec(dur_div)
                    continue
                if tag != "note":
                    continue

                # Skip cue / non-sounding / grace-only notes for timeline mapping.
                if item.attrib.get("print-object") == "no":
                    continue
                if _child(item, "cue") is not None:
                    continue

                dur_div = float(_text(item, "duration", "0") or "0")
                is_chord = _child(item, "chord") is not None
                is_rest = _child(item, "rest") is not None
                is_grace = _child(item, "grace") is not None
                start_div = current_div
                start_sec = current_sec
                duration_sec = _divs_to_sec(dur_div)
                if not is_chord and not is_grace:
                    current_div += dur_div
                    current_sec += duration_sec
                if is_rest or is_grace or dur_div <= 0:
                    continue

                # beat_type: duration of one beat in quarters (4 → 1.0 quarter)
                beat_unit = 4.0 / max(beat_type, 1e-6)
                beat = (start_div - measure_start_div) / (divisions * beat_unit) + 1.0
                written = _pitch_midi(item)
                concert = None if written is None else int(written + transpose_chromatic)
                note_index += 1
                events.append(
                    NoteEvent(
                        note_id=f"{current_part_id or 'part'}_m{measure_no}_n{note_index}",
                        measure=measure_no,
                        beat=float(beat),
                        pitch_midi=concert,
                        start_sec=float(start_sec),
                        end_sec=float(start_sec + duration_sec),
                        duration_sec=float(duration_sec),
                        part_id=current_part_id,
                        voice=_text(item, "voice"),
                    )
                )

            # Expand multi-measure rest: advance N full bars, skip N-1 placeholders.
            if multi_rest_bars > 0:
                beat_unit = 4.0 / max(beat_type, 1e-6)
                measure_divs = beats * beat_unit * divisions
                measure_sec = _divs_to_sec(measure_divs)
                current_div = measure_start_div + multi_rest_bars * measure_divs
                current_sec = measure_start_sec + multi_rest_bars * measure_sec
                skip_measures = max(multi_rest_bars - 1, 0)

    events.sort(key=lambda event: (event.start_sec, event.measure, event.beat, event.note_id))
    return events
