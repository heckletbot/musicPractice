"""PitchTrackData contract + detect_pitch public API tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from music_practice.contract import (
    PITCH_TRACK_DATA_SCHEMA,
    PITCH_TRACK_DATA_VERSION,
    PitchTrackDataError,
    dump_pitch_track_data,
    load_pitch_track_data,
    pitch_track_data_to_pitch_track,
    pitch_track_to_pitch_track_data,
    validate_pitch_track_data,
)
from music_practice.pitch.detector import PitchFrame, PitchTrack, detect_pitch


def _sample_track() -> PitchTrack:
    return PitchTrack(
        sample_rate=22050,
        frame_size=512,
        window_duration_sec=512 / 22050,
        frames=[
            PitchFrame(0.0, 440.0, 69.0, "A4", True),
            PitchFrame(512 / 22050, None, -1.0, None, False),
        ],
    )


def test_validate_rejects_bad_schema():
    with pytest.raises(PitchTrackDataError):
        validate_pitch_track_data({"schema": "other", "schema_version": "1.0"})


def test_pitch_track_roundtrip(tmp_path: Path):
    track = _sample_track()
    data = pitch_track_to_pitch_track_data(track)
    assert data["schema"] == PITCH_TRACK_DATA_SCHEMA
    assert data["schema_version"] == PITCH_TRACK_DATA_VERSION
    assert len(data["frames"]) == 2

    path = dump_pitch_track_data(data, tmp_path / "track.json")
    loaded = load_pitch_track_data(path)
    back = pitch_track_data_to_pitch_track(loaded)
    assert back.sample_rate == track.sample_rate
    assert back.frames[0].frequency_hz == pytest.approx(440.0)
    assert back.frames[1].voiced is False


def test_detect_pitch_short_pcm_returns_empty_frames():
    # Shorter than one frame → empty frames, still valid PitchTrackData
    audio = np.zeros(100, dtype=np.float32)
    data = detect_pitch(audio, sample_rate=22050, tempo=120.0)
    assert data["schema"] == PITCH_TRACK_DATA_SCHEMA
    assert data["frames"] == []
    assert data["sample_rate"] == 22050


def test_detect_pitch_emptyish_still_validates():
    audio = np.zeros(512, dtype=np.float32)
    data = detect_pitch(audio, sample_rate=22050, tempo=120.0)
    validated = validate_pitch_track_data(data)
    assert validated["frame_size"] == 512
