"""Public helpers for calling and inspecting music-practice modules."""

from music_practice.start_detect import (
    AudioFrame,
    StartDetectSession,
    load_score_template_map,
    resolve_template_id,
)
from music_practice.utils.api import (
    analyze_pitch_segment,
    analyze_pitch_segment_from_track,
    analyze_pitch_track,
    build_score_intervals,
    detect_start_note,
    evaluate_rhythm_audio,
    evaluate_rhythm_from_track,
    get_score,
    get_start_note,
    import_score,
    list_score_summaries,
    measure_interval_id,
    parse_score,
    score_summary,
)
from music_practice.utils.observe import format_observation, observe, to_observable_dict

__all__ = [
    "AudioFrame",
    "StartDetectSession",
    "analyze_pitch_segment",
    "analyze_pitch_segment_from_track",
    "analyze_pitch_track",
    "build_score_intervals",
    "detect_start_note",
    "evaluate_rhythm_audio",
    "evaluate_rhythm_from_track",
    "format_observation",
    "get_score",
    "get_start_note",
    "import_score",
    "list_score_summaries",
    "load_score_template_map",
    "measure_interval_id",
    "observe",
    "parse_score",
    "resolve_template_id",
    "score_summary",
    "to_observable_dict",
]
