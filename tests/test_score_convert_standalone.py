"""convert_musicxml works without importing recognize."""

from __future__ import annotations

from pathlib import Path

MINIMAL_MUSICXML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC
  "-//Recordare//DTD MusicXML 3.1 Partwise//EN"
  "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="3.1">
  <part-list>
    <score-part id="P1"><part-name>Music</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <key><fifths>0</fifths></key>
        <time><beats>4</beats><beat-type>4</beat-type></time>
        <clef><sign>G</sign><line>2</line></clef>
      </attributes>
      <direction placement="above">
        <direction-type><metronome><beat-unit>quarter</beat-unit><per-minute>120</per-minute></metronome></direction-type>
        <sound tempo="120"/>
      </direction>
      <note>
        <pitch><step>C</step><octave>4</octave></pitch>
        <duration>1</duration>
        <voice>1</voice>
        <type>quarter</type>
      </note>
      <note>
        <pitch><step>D</step><octave>4</octave></pitch>
        <duration>1</duration>
        <voice>1</voice>
        <type>quarter</type>
      </note>
      <note>
        <rest/>
        <duration>2</duration>
        <voice>1</voice>
        <type>half</type>
      </note>
    </measure>
  </part>
</score-partwise>
"""


def test_convert_musicxml_to_score_data(tmp_path: Path):
    xml_path = tmp_path / "mini.musicxml"
    xml_path.write_text(MINIMAL_MUSICXML, encoding="utf-8")

    # Import only score converter — must not require recognize.
    from music_practice.score import convert_musicxml

    data = convert_musicxml(xml_path, score_id="mini_demo")
    assert data["schema"] == "music_practice.score_data"
    assert data["score_id"] == "mini_demo"
    assert data["tempo"] == 120.0
    assert len(data["notes"]) == 2
    assert data["notes"][0]["pitch"] in {"C4", "C"}
    assert data["notes"][0]["note_index_in_measure"] == 1
    assert data["notes"][1]["note_index_in_measure"] == 2
    assert data["notes"][0]["onset"] == 0.0
    assert data["notes"][0]["pitch_midi"] is not None
