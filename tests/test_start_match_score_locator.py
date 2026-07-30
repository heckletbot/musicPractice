from __future__ import annotations

import numpy as np

from music_practice.start_match.locator.core import _to_candidate
from music_practice.start_match.matcher.dtw import subsequence_dtw_global_topk
from music_practice.start_match.matcher.global_match import GlobalMatchResult
from music_practice.start_match.score import load_note_events, parse_musicxml, save_note_events
from music_practice.start_match.score.calibrate import calibrate_note_events_to_template
from music_practice.start_match.types import NoteEvent


def test_parse_musicxml_and_store_roundtrip(tmp_path):
    xml = tmp_path / "score.musicxml"
    xml.write_text(
        """<?xml version="1.0"?>
<score-partwise version="3.1">
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>2</divisions>
      </attributes>
      <direction>
        <direction-type><metronome><beat-unit>quarter</beat-unit><per-minute>120</per-minute></metronome></direction-type>
      </direction>
      <note>
        <pitch><step>C</step><octave>4</octave></pitch>
        <duration>2</duration>
        <voice>1</voice>
      </note>
      <note>
        <pitch><step>D</step><octave>4</octave></pitch>
        <duration>2</duration>
        <voice>1</voice>
      </note>
    </measure>
  </part>
</score-partwise>
""",
        encoding="utf-8",
    )

    events = parse_musicxml(xml)
    assert [event.pitch_midi for event in events] == [60, 62]
    assert events[0].measure == 1
    assert events[0].beat == 1.0
    assert events[1].start_sec == 0.5

    out = tmp_path / "note_events.json"
    save_note_events(out, events)
    assert load_note_events(out) == events


def test_parse_musicxml_chord_shares_onset(tmp_path):
    """Primary + <chord/> tones must start together; only one eighth advances time."""
    xml = tmp_path / "chord.musicxml"
    xml.write_text(
        """<?xml version="1.0"?>
<score-partwise version="3.1">
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>256</divisions>
        <time><beats>4</beats><beat-type>4</beat-type></time>
      </attributes>
      <direction>
        <direction-type><metronome><beat-unit>quarter</beat-unit><per-minute>116</per-minute></metronome></direction-type>
      </direction>
      <note>
        <pitch><step>E</step><octave>5</octave></pitch>
        <duration>128</duration>
        <voice>1</voice>
        <type>eighth</type>
      </note>
      <note>
        <chord/>
        <pitch><step>A</step><octave>5</octave></pitch>
        <duration>128</duration>
        <type>eighth</type>
      </note>
      <note>
        <rest/>
        <duration>896</duration>
        <voice>1</voice>
      </note>
    </measure>
  </part>
</score-partwise>
""",
        encoding="utf-8",
    )

    events = parse_musicxml(xml)
    assert len(events) == 2
    eighth = (128 / 256) * (60 / 116)
    assert events[0].start_sec == events[1].start_sec == 0.0
    assert events[0].beat == events[1].beat == 1.0
    assert abs(events[0].duration_sec - eighth) < 1e-9
    assert abs(events[1].duration_sec - eighth) < 1e-9
    assert {events[0].pitch_midi, events[1].pitch_midi} == {76, 81}


def test_parse_musicxml_tempo_offset_applies_at_bar_end(tmp_path):
    """Metronome at measure start with near-full offset keeps the bar at old tempo."""
    xml = tmp_path / "tempo_offset.musicxml"
    xml.write_text(
        """<?xml version="1.0"?>
<score-partwise version="3.1">
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>256</divisions>
        <time><beats>4</beats><beat-type>4</beat-type></time>
      </attributes>
      <direction>
        <direction-type><metronome><beat-unit>quarter</beat-unit><per-minute>68</per-minute></metronome></direction-type>
      </direction>
      <note>
        <pitch><step>C</step><octave>4</octave></pitch>
        <duration>256</duration>
        <voice>1</voice>
      </note>
      <note><rest/><duration>768</duration><voice>1</voice></note>
    </measure>
    <measure number="2">
      <direction>
        <direction-type><metronome><beat-unit>quarter</beat-unit><per-minute>132</per-minute></metronome></direction-type>
        <offset sound="no">1023</offset>
      </direction>
      <note><rest/><duration>1024</duration><voice>1</voice></note>
    </measure>
    <measure number="3">
      <note>
        <pitch><step>D</step><octave>4</octave></pitch>
        <duration>256</duration>
        <voice>1</voice>
      </note>
    </measure>
  </part>
</score-partwise>
""",
        encoding="utf-8",
    )

    events = parse_musicxml(xml)
    assert len(events) == 2
    # m1 remaining 3 beats @68 + m2 whole rest mostly @68 (132 only at bar-end offset)
    gap = 3 * (60 / 68) + 4 * (60 / 68)
    # 1 division at bar-end may already be at 132; allow a tiny mix.
    assert abs(events[1].start_sec - (events[0].end_sec + gap)) < 5e-3
    assert abs(events[1].duration_sec - (60 / 132)) < 1e-6


def test_global_topk_returns_diverse_repeated_candidates():
    query = np.eye(4, dtype=np.float32)
    template = np.zeros((20, 4), dtype=np.float32)
    template[2:6] = query
    template[12:16] = query

    results = subsequence_dtw_global_topk(template, query, top_k=2, min_separation_frames=4)
    starts = sorted(start for _, start, _ in results)
    assert starts == [2, 12]


def test_calibrate_note_events_stretches_to_template_duration():
    events = [
        NoteEvent("n1", measure=1, beat=1.0, pitch_midi=60, start_sec=0.0, end_sec=1.0, duration_sec=1.0),
        NoteEvent("n2", measure=1, beat=2.0, pitch_midi=62, start_sec=1.0, end_sec=2.0, duration_sec=1.0),
    ]
    calibrated, cal = calibrate_note_events_to_template(events, template_duration_sec=10.0)
    assert cal.scale == 5.0
    assert calibrated[-1].end_sec == 10.0
    assert calibrated[0].start_sec == 0.0


def test_candidate_maps_seconds_to_nearest_note():
    events = [
        NoteEvent("n1", measure=1, beat=1.0, pitch_midi=60, start_sec=0.0, end_sec=0.5, duration_sec=0.5),
        NoteEvent("n2", measure=1, beat=2.0, pitch_midi=62, start_sec=0.5, end_sec=1.0, duration_sec=0.5),
    ]
    result = GlobalMatchResult(
        start_sec=0.62,
        end_sec=1.0,
        start_frame=0,
        end_frame=1,
        start_center_frame=0,
        end_center_frame=1,
        normalized_cost=0.1,
        score=0.9,
        query_duration_sec=0.5,
    )
    candidate = _to_candidate(result, events, rank=1)
    assert candidate.note_id == "n2"
    assert candidate.measure == 1
    assert candidate.beat == 2.0
