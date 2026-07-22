from __future__ import annotations

import json
from pathlib import Path

import pytest
import soundfile as sf

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "start_detect"
MANIFEST_PATH = FIXTURES / "manifest.json"
CATALOG_PATH = FIXTURES / "catalog.json"


@pytest.fixture(scope="module")
def start_detect_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        pytest.skip("start_detect manifest missing")
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_start_detect_catalog_has_three_pieces():
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    piece_ids = {piece["piece_id"] for piece in catalog["pieces"]}
    assert piece_ids == {"winter_1973", "viktor_tale", "meili_flute"}


def test_start_detect_manifest_structure(start_detect_manifest: dict):
    assert start_detect_manifest["case_count"] == 30
    assert len(start_detect_manifest["pieces"]) == 3
    assert len(start_detect_manifest["cases"]) == 30

    piece_ids = {piece["piece_id"] for piece in start_detect_manifest["pieces"]}
    assert piece_ids == {"winter_1973", "viktor_tale", "meili_flute"}


def test_start_detect_query_files_exist(start_detect_manifest: dict):
    sample_rate = start_detect_manifest["sample_rate"]
    query_duration_sec = start_detect_manifest["query_duration_sec"]

    for case in start_detect_manifest["cases"]:
        query_path = FIXTURES / case["query_wav"]
        assert query_path.exists(), case["case_id"]

        audio, sr = sf.read(str(query_path))
        assert sr == sample_rate
        assert audio.ndim == 1
        assert abs(len(audio) / sr - query_duration_sec) < 0.05
        assert case["content_sec"] >= 1.0


def test_start_detect_templates_and_scores(start_detect_manifest: dict):
    for piece in start_detect_manifest["pieces"]:
        template_meta = FIXTURES / piece["template_dir"] / "meta.json"
        note_events = FIXTURES / piece["template_dir"] / "note_events.json"
        score_meta = FIXTURES / "scores" / piece["score_id"] / "meta.json"

        assert template_meta.exists(), piece["piece_id"]
        assert note_events.exists(), piece["piece_id"]
        assert score_meta.exists(), piece["piece_id"]

        for case in piece["cases"]:
            assert case["template_sec"] > 0
            assert case["expected_note_event"]["measure"] == case["expected_start_note"]["measure"]
