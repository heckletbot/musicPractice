"""music2seq: template building and tempo-tolerant audio alignment."""

from music2seq.locator import locate_against_template, locate_query
from music2seq.matcher.core import match_against_template, match_query
from music2seq.template import build_template, load_template
from music2seq.types import (
    FEATURE_KIND_MEL,
    FEATURE_KIND_PITCH,
    FeatureConfig,
    MatchCandidate,
    MatchResult,
    LocateCandidate,
    LocateContext,
    LocateResult,
    NoteEvent,
    PitchFeatureConfig,
    QUERY_DURATION_MAX_SEC,
    QUERY_DURATION_MIN_SEC,
    validate_query_duration,
    validate_template_duration,
)
from music2seq.utils import convert_m4a_dir, find_ffmpeg, m4a_to_mp3, audio_to_raw_wav

__version__ = "0.1.0"

__all__ = [
    "FEATURE_KIND_MEL",
    "FEATURE_KIND_PITCH",
    "FeatureConfig",
    "MatchCandidate",
    "MatchResult",
    "LocateCandidate",
    "LocateContext",
    "LocateResult",
    "NoteEvent",
    "PitchFeatureConfig",
    "QUERY_DURATION_MAX_SEC",
    "QUERY_DURATION_MIN_SEC",
    "build_template",
    "load_template",
    "locate_against_template",
    "locate_query",
    "match_against_template",
    "match_query",
    "validate_query_duration",
    "validate_template_duration",
    "convert_m4a_dir",
    "find_ffmpeg",
    "m4a_to_mp3",
    "audio_to_raw_wav",
]
