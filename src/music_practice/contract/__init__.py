"""Fixed interface contract between MusicXML conversion and recognition."""

from music_practice.contract.bridge import (
    find_start_index,
    score_data_to_score,
    score_to_score_data,
    slice_practice_notes,
)
from music_practice.contract.schema import (
    RECOGNIZE_RESULT_SCHEMA,
    RECOGNIZE_RESULT_VERSION,
    SCORE_DATA_SCHEMA,
    SCORE_DATA_VERSION,
    SUPPORTED_SCORE_DATA_VERSIONS,
)
from music_practice.contract.validate import (
    ScoreDataError,
    dump_score_data,
    load_score_data,
    validate_score_data,
)

__all__ = [
    "RECOGNIZE_RESULT_SCHEMA",
    "RECOGNIZE_RESULT_VERSION",
    "SCORE_DATA_SCHEMA",
    "SCORE_DATA_VERSION",
    "SUPPORTED_SCORE_DATA_VERSIONS",
    "ScoreDataError",
    "dump_score_data",
    "find_start_index",
    "load_score_data",
    "score_data_to_score",
    "score_to_score_data",
    "slice_practice_notes",
    "validate_score_data",
]
