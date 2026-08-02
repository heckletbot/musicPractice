"""Score MusicXML parser: chord shared onset + multiple-rest bar duration."""

from __future__ import annotations

from pathlib import Path

from music_practice.score.parser import ParseContext, parse_musicxml


def test_chord_notes_share_onset(tmp_path: Path):
    xml = tmp_path / "chord.musicxml"
    xml.write_text(
        """<?xml version="1.0"?>
<score-partwise version="3.1">
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>2</divisions>
        <time><beats>4</beats><beat-type>4</beat-type></time>
      </attributes>
      <direction>
        <direction-type>
          <metronome><beat-unit>quarter</beat-unit><per-minute>120</per-minute></metronome>
        </direction-type>
        <sound tempo="120"/>
      </direction>
      <note>
        <pitch><step>C</step><octave>4</octave></pitch>
        <duration>1</duration>
        <voice>1</voice>
      </note>
      <note>
        <chord/>
        <pitch><step>E</step><octave>4</octave></pitch>
        <duration>1</duration>
        <voice>1</voice>
      </note>
      <note>
        <pitch><step>G</step><octave>4</octave></pitch>
        <duration>1</duration>
        <voice>1</voice>
      </note>
    </measure>
  </part>
</score-partwise>
""",
        encoding="utf-8",
    )
    notes, _meta = parse_musicxml(xml)
    assert len(notes) == 3
    assert notes[0].onset == notes[1].onset == 0.0
    assert notes[0].pitch == "C4"
    assert notes[1].pitch == "E4"
    # Eighth at 120 BPM = 0.25s; next note after the chord
    assert notes[2].onset == 0.25
    assert notes[2].pitch == "G4"


def test_measure_duration_sec_uses_time_signature():
    ctx_44 = ParseContext(tempo_bpm=120.0, beats=4, beat_type=4)
    assert ctx_44.measure_duration_sec == 2.0  # 4 quarters @ 0.5s
    ctx_68 = ParseContext(tempo_bpm=60.0, beats=6, beat_type=8)
    # 6 eighths = 3 quarters @ 1.0s → 3.0s
    assert ctx_68.measure_duration_sec == 3.0


def test_multiple_rest_advances_by_bar_times_count(tmp_path: Path):
    xml = tmp_path / "multirest.musicxml"
    xml.write_text(
        """<?xml version="1.0"?>
<score-partwise version="3.1">
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <time><beats>6</beats><beat-type>8</beat-type></time>
        <measure-style><multiple-rest>2</multiple-rest></measure-style>
      </attributes>
      <direction>
        <direction-type>
          <metronome><beat-unit>quarter</beat-unit><per-minute>60</per-minute></metronome>
        </direction-type>
        <sound tempo="60"/>
      </direction>
    </measure>
    <measure number="2"/>
    <measure number="3">
      <note>
        <pitch><step>C</step><octave>4</octave></pitch>
        <duration>1</duration>
        <voice>1</voice>
      </note>
    </measure>
  </part>
</score-partwise>
""",
        encoding="utf-8",
    )
    notes, meta = parse_musicxml(xml)
    assert meta.time_signature == "6/8"
    assert len(notes) == 1
    # 2 bars * 3.0s = 6.0s before the first note in m3
    assert notes[0].onset == 6.0
    assert notes[0].measure == 3
