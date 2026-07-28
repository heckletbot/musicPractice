"""Unit test: dotted-quarter metronome converts to quarter BPM."""
from xml.etree import ElementTree as ET

from music_practice.score.parser import _tempo_from_direction


def test_dotted_quarter_metronome_to_quarter_bpm():
    direction = ET.fromstring(
        """
        <direction>
          <direction-type>
            <metronome>
              <beat-unit>quarter</beat-unit>
              <beat-unit-dot/>
              <per-minute>67</per-minute>
            </metronome>
          </direction-type>
        </direction>
        """
    )
    assert _tempo_from_direction(direction) == 67 * 1.5


def test_sound_tempo_prefers_quarter_bpm():
    direction = ET.fromstring(
        """
        <direction>
          <direction-type>
            <metronome>
              <beat-unit>quarter</beat-unit>
              <beat-unit-dot/>
              <per-minute>67</per-minute>
            </metronome>
          </direction-type>
          <sound tempo="100.5"/>
        </direction>
        """
    )
    assert _tempo_from_direction(direction) == 100.5
