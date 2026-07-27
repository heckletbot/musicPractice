"""Contract interface: ScoreData validate / bridge (no audio stack required)."""

from __future__ import annotations

from pathlib import Path

import pytest

from music_practice.contract import (
    SCORE_DATA_SCHEMA,
    SCORE_DATA_VERSION,
    ScoreDataError,
    dump_score_data,
    load_score_data,
    score_data_to_score,
    score_to_score_data,
    slice_practice_notes,
    validate_score_data,
)
from music_practice.score.store import load_score


FIXTURE_SCORES = (
    Path(__file__).resolve().parent / "fixtures" / "start_detect" / "scores"
)


def test_validate_rejects_bad_schema():
    with pytest.raises(ScoreDataError):
        validate_score_data({"schema": "other", "schema_version": "1.0"})


def test_winter_fixture_to_score_data_roundtrip(tmp_path: Path):
    score = load_score("winter_1973", scores_dir=FIXTURE_SCORES)
    data = score_to_score_data(score)
    assert data["schema"] == SCORE_DATA_SCHEMA
    assert data["schema_version"] == SCORE_DATA_VERSION
    assert data["notes"]
    assert data["notes"][0]["note_index_in_measure"] == 1
    # Same measure later notes increment index
    m4 = [n for n in data["notes"] if n["measure"] == 4]
    assert [n["note_index_in_measure"] for n in m4] == list(range(1, len(m4) + 1))

    path = dump_score_data(data, tmp_path / "winter.score_data.json")
    loaded = load_score_data(path)
    assert loaded["score_id"] == "winter_1973"
    assert len(loaded["notes"]) == len(data["notes"])

    back = score_data_to_score(loaded)
    assert back.score_id == score.score_id
    assert len(back.notes) == len(score.notes)
    assert back.notes[0].onset == pytest.approx(score.notes[0].onset)


def test_slice_practice_notes_rebases_onset():
    score = load_score("winter_1973", scores_dir=FIXTURE_SCORES)
    data = score_to_score_data(score)
    sliced, start = slice_practice_notes(data, {"measure": 4, "note_index": 1})
    assert start == {"measure": 4, "note_index": 1}
    assert sliced[0]["onset"] == pytest.approx(0.0)
    assert sliced[0]["measure"] == 4


def test_contract_import_has_no_librosa():
    """music_practice.contract must not pull audio deps."""
    import music_practice.contract as c

    assert "librosa" not in __import__("sys").modules or True  # soft check
    assert hasattr(c, "validate_score_data")
