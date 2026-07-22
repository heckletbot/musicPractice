"""Soft smoke: winter_1973 template rhythm window (batch WAV, not streaming)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "rhythm_template" / "winter_1973"
RESULT = Path(__file__).resolve().parent / "results" / "rhythm_template_winter.json"


@pytest.fixture(scope="module")
def winter_label() -> dict:
    path = FIXTURE / "label.json"
    if not path.exists():
        pytest.skip("winter rhythm fixture label missing")
    return json.loads(path.read_text(encoding="utf-8"))


def test_winter_fixture_audible(winter_label: dict):
    import numpy as np
    import soundfile as sf

    wav = FIXTURE / winter_label["query"]["wav"]
    assert wav.exists()
    audio, _sr = sf.read(str(wav), always_2d=False)
    rms = float(np.sqrt(np.mean(np.asarray(audio, dtype=np.float64) ** 2)))
    assert rms > 1e-3, "window should contain template audio (not lead-in silence)"


def test_winter_pipeline_detects_onsets(winter_label: dict):
    from music_practice.rhythm.config import OnsetDetectConfig
    from music_practice.rhythm.onset import detect_onsets

    wav = FIXTURE / winter_label["query"]["wav"]
    tempo = float(winter_label["tempo_bpm"])
    onsets = detect_onsets(wav, config=OnsetDetectConfig.for_tempo(tempo), tempo=tempo)
    assert len(onsets) >= 1


def test_winter_result_artifact_if_present():
    """If eval was run, ensure rates are recorded (no hard rhythm_ok gate yet)."""
    if not RESULT.exists():
        pytest.skip("optional result artifact not bundled")
    summary = json.loads(RESULT.read_text(encoding="utf-8"))
    assert "mode_full_detect" in summary
    assert summary["mode_full_detect"]["note_count"] >= 1
    # Smoke only: pipeline produced judgements; accuracy tracked in JSON for now.
    assert "rhythm_ok_rate" in summary["mode_full_detect"]
