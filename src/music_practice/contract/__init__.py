"""Fixed interface contract between MusicXML conversion and recognition."""

from music_practice.contract.bridge import (
    coerce_pitch_track,
    find_start_index,
    pitch_track_data_to_pitch_track,
    pitch_track_to_pitch_track_data,
    score_data_to_score,
    score_to_score_data,
    slice_practice_notes,
)
from music_practice.contract.schema import (
    PITCH_TRACK_DATA_SCHEMA,
    PITCH_TRACK_DATA_VERSION,
    RECOGNIZE_RESULT_SCHEMA,
    RECOGNIZE_RESULT_VERSION,
    SCORE_DATA_SCHEMA,
    SCORE_DATA_VERSION,
    SUPPORTED_PITCH_TRACK_DATA_VERSIONS,
    SUPPORTED_SCORE_DATA_VERSIONS,
)
from music_practice.contract.validate import (
    PitchTrackDataError,
    ScoreDataError,
    dump_pitch_track_data,
    dump_score_data,
    load_pitch_track_data,
    load_score_data,
    validate_pitch_track_data,
    validate_score_data,
)

__all__ = [
    "PITCH_TRACK_DATA_SCHEMA",
    "PITCH_TRACK_DATA_VERSION",
    "RECOGNIZE_RESULT_SCHEMA",
    "RECOGNIZE_RESULT_VERSION",
    "SCORE_DATA_SCHEMA",
    "SCORE_DATA_VERSION",
    "SUPPORTED_PITCH_TRACK_DATA_VERSIONS",
    "SUPPORTED_SCORE_DATA_VERSIONS",
    "PitchTrackDataError",
    "ScoreDataError",
    "coerce_pitch_track",
    "dump_pitch_track_data",
    "dump_score_data",
    "find_start_index",
    "load_pitch_track_data",
    "load_score_data",
    "pitch_track_data_to_pitch_track",
    "pitch_track_to_pitch_track_data",
    "score_data_to_score",
    "score_to_score_data",
    "slice_practice_notes",
    "validate_pitch_track_data",
    "validate_score_data",
]
