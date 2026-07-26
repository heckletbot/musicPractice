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


def _direction_offset_divs(direction: ET.Element) -> float:
    offset = _child(direction, "offset")
    if offset is None or offset.text is None:
        return 0.0
    try:
        return float(offset.text.strip())
    except ValueError:
        return 0.0


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
    Tempo directions honor ``<offset>`` (Sibelius often parks a new metronome at
    bar-end with a near-full-measure offset while still writing the direction at
    measure start). Pitch is stored as **concert** MIDI when ``<transpose>`` is
    present.
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
        # Onset of the most recent non-chord note; chord tones reuse this cursor.
        chord_anchor_div = 0.0
        chord_anchor_sec = 0.0
        # Time signature (defaults 4/4); needed to expand <multiple-rest>.
        beats = 4.0
        beat_type = 4.0
        # Concert pitch = written + chromatic (Bb clarinet typically -2).
        transpose_chromatic = 0
        # After consuming a multi-measure rest of N bars, skip the next N-1
        # empty placeholder measures so duration is not double-counted.
        skip_measures = 0
        # Deferred tempo changes: (absolute divisions, bpm), sorted by div.
        pending_tempos: list[tuple[float, float]] = []

        def _sec_per_quarter() -> float:
            return 60.0 / max(tempo_bpm, 1e-6)

        def _apply_due_tempos() -> None:
            nonlocal tempo_bpm
            while pending_tempos and pending_tempos[0][0] <= current_div + 1e-9:
                _, tempo_bpm = pending_tempos.pop(0)

        def _advance(dur_div: float) -> float:
            """Advance the cursor by ``dur_div``, applying mid-span tempo changes."""
            nonlocal current_div, current_sec, tempo_bpm
            remaining = float(dur_div)
            advanced_sec = 0.0
            while remaining > 1e-12:
                _apply_due_tempos()
                next_change = None
                for at, _bpm in pending_tempos:
                    if at > current_div + 1e-12:
                        next_change = at
                        break
                if next_change is not None and next_change < current_div + remaining - 1e-12:
                    chunk = next_change - current_div
                else:
                    chunk = remaining
                sec = (chunk / divisions) * _sec_per_quarter()
                current_div += chunk
                current_sec += sec
                advanced_sec += sec
                remaining -= chunk
            _apply_due_tempos()
            return advanced_sec

        def _schedule_tempo(bpm: float, offset_div: float) -> None:
            at = current_div + max(0.0, offset_div)
            pending_tempos.append((at, float(bpm)))
            pending_tempos.sort(key=lambda item: item[0])
            _apply_due_tempos()

        for measure in _children(part, "measure"):
            if skip_measures > 0:
                skip_measures -= 1
                continue

            measure_no_text = measure.attrib.get("number", "0").split(".")[0]
            measure_no = int(measure_no_text or "0")
            measure_start_div = current_div
            measure_start_sec = current_sec
            multi_rest_bars = 0
            _apply_due_tempos()

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
                        _schedule_tempo(tempo, _direction_offset_divs(item))
                    continue
                if tag == "backup":
                    dur_div = float(_text(item, "duration", "0") or "0")
                    # Backup does not re-open earlier tempo history; shift cursor only.
                    current_div -= dur_div
                    current_sec -= (dur_div / divisions) * _sec_per_quarter()
                    continue
                if tag == "forward":
                    _advance(float(_text(item, "duration", "0") or "0"))
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
                # MusicXML order: primary note, then <chord/> tones. Primary advances
                # the cursor; chord tones must keep the primary onset, not the advanced time.
                if is_chord:
                    start_div = chord_anchor_div
                    start_sec = chord_anchor_sec
                    duration_sec = (dur_div / divisions) * _sec_per_quarter()
                else:
                    start_div = current_div
                    start_sec = current_sec
                    if not is_grace:
                        chord_anchor_div = current_div
                        chord_anchor_sec = current_sec
                        duration_sec = _advance(dur_div)
                    else:
                        duration_sec = (dur_div / divisions) * _sec_per_quarter()
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
                _advance(multi_rest_bars * measure_divs)
                skip_measures = max(multi_rest_bars - 1, 0)

    events.sort(key=lambda event: (event.start_sec, event.measure, event.beat, event.note_id))
    return events
