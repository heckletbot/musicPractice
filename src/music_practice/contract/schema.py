"""Fixed ScoreData / PitchTrackData / RecognizeResult contract (no audio / XML deps)."""

from __future__ import annotations

SCORE_DATA_SCHEMA = "music_practice.score_data"
SCORE_DATA_VERSION = "1.0"

PITCH_TRACK_DATA_SCHEMA = "music_practice.pitch_track_data"
PITCH_TRACK_DATA_VERSION = "1.0"

RECOGNIZE_RESULT_SCHEMA = "music_practice.recognize_result"
RECOGNIZE_RESULT_VERSION = "1.0"

SUPPORTED_SCORE_DATA_VERSIONS = frozenset({"1.0"})
SUPPORTED_PITCH_TRACK_DATA_VERSIONS = frozenset({"1.0"})
