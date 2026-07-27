"""recognize() consumes ScoreData only (inject path, no MusicXML)."""

from __future__ import annotations

from pathlib import Path

import pytest

from music_practice.contract import score_to_score_data
from music_practice.pitch.detector import PitchFrame, PitchTrack
from music_practice.recognize import recognize_from_track
from music_practice.score.store import load_score


FIXTURE_SCORES = (
    Path(__file__).resolve().parent / "fixtures" / "start_detect" / "scores"
)

SR = 22050
FRAME = 512
WINDOW = FRAME / SR


def _track_for_notes(notes: list[dict], *, midi_override: dict[int, float] | None = None) -> PitchTrack:
    """Voiced frames covering each practice note window."""
    frames: list[PitchFrame] = []
    end = max(n["onset"] + n["duration"] for n in notes) + WINDOW
    t = 0.0
    while t < end:
        midi = -1.0
        voiced = False
        for i, n in enumerate(notes):
            if n["onset"] <= t < n["onset"] + n["duration"]:
                midi = float((midi_override or {}).get(i, n["pitch_midi"]))
                voiced = True
                break
        frames.append(
            PitchFrame(
                time_sec=t,
                frequency_hz=440.0 if voiced else None,
                pitch_midi=midi if voiced else -1.0,
                pitch="X" if voiced else None,
                voiced=voiced,
            )
        )
        t += WINDOW
    return PitchTrack(
        sample_rate=SR,
        frame_size=FRAME,
        window_duration_sec=WINDOW,
        frames=frames,
    )


def test_recognize_from_score_data_without_musicxml():
    score = load_score("winter_1973", scores_dir=FIXTURE_SCORES)
    score_data = score_to_score_data(score)
    # Take first 3 notes of measure 4 as a mini phrase
    start_from = {"measure": 4, "note_index": 1}
    from music_practice.contract import slice_practice_notes

    practice, _ = slice_practice_notes(score_data, start_from)
    phrase = practice[:3]
    onsets = [float(n["onset"]) for n in phrase]
    # Build a temporary score_data containing only these (already rebased)
    mini = dict(score_data)
    # Re-stamp absolute-like fields: use rebased notes but keep schema
    mini_notes = []
    for n in phrase:
        item = dict(n)
        # slice already rebased; for mini score_data treat as absolute from 0
        mini_notes.append(item)
    mini["notes"] = mini_notes

    track = _track_for_notes(mini_notes)
    result = recognize_from_track(
        mini,
        detected_onsets=onsets,
        track=track,
        start_from=None,
        config={"duration_window_mode": "anchored_grid", "pitch_tolerance_semitones": 1.0},
    )
    assert result["schema"] == "music_practice.recognize_result"
    assert result["summary"]["total_notes"] == 3
    assert result["summary"]["correct_count"] == 3
    assert all(n["overall_correct"] for n in result["notes"])
    assert result["notes"][0]["measure"] == 4
    assert result["notes"][0]["note_index_in_measure"] == 1


def test_recognize_reports_pitch_error():
    score = load_score("winter_1973", scores_dir=FIXTURE_SCORES)
    score_data = score_to_score_data(score)
    from music_practice.contract import slice_practice_notes

    practice, _ = slice_practice_notes(score_data, {"measure": 4, "note_index": 1})
    phrase = practice[:1]
    mini = dict(score_data)
    mini["notes"] = [dict(phrase[0])]
    track = _track_for_notes(mini["notes"], midi_override={0: float(mini["notes"][0]["pitch_midi"]) + 5})
    result = recognize_from_track(
        mini,
        detected_onsets=[0.0],
        track=track,
        config={"pitch_tolerance_semitones": 1.0, "duration_window_mode": "anchored_grid"},
    )
    assert result["notes"][0]["pitch_ok"] is False
    assert "pitch" in result["notes"][0]["error_dims"]
    assert result["notes"][0]["overall_correct"] is False
    assert result["summary"]["pitch_error_count"] == 1
