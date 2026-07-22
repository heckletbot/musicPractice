from __future__ import annotations

import json

import numpy as np
import pytest
import soundfile as sf

from music_practice.score.store import load_score
from music_practice.start_detect import AudioFrame, StartDetectContext, StartDetectSession
from music_practice.types import StartNoteRef

from conftest import START_DETECT_FIXTURES

MANIFEST_PATH = START_DETECT_FIXTURES / "manifest.json"
FRAME_SAMPLES = 86


@pytest.fixture(scope="module")
def stream_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        pytest.skip("start_detect manifest missing")
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_session_push_pcm_frames_meili(stream_manifest: dict):
    """Push PCM chunks into StartDetectSession until started (meili only)."""
    piece = next(p for p in stream_manifest["pieces"] if p["piece_id"] == "meili_flute")
    case = piece["cases"][0]
    score = load_score(piece["score_id"], scores_dir=START_DETECT_FIXTURES / "scores")
    ref = StartNoteRef(**case["expected_start_note"])
    pcm, sr = sf.read(str(START_DETECT_FIXTURES / case["query_wav"]), dtype="float32")
    if pcm.ndim > 1:
        pcm = pcm.mean(axis=1)

    ctx = StartDetectContext(
        min_query_sec=1.0,
        max_query_sec=2.0,
        dtw_interval_sec=0.0,
        score_threshold=0.35,
    )
    session = StartDetectSession()
    session.open(
        score,
        template_id=piece["template_id"],
        start_note=ref,
        templates_dir=START_DETECT_FIXTURES / "templates",
        context=ctx,
        sample_rate=sr,
    )
    result = None
    chunk = max(FRAME_SAMPLES, int(0.1 * sr))
    seq = 0
    for start in range(0, len(pcm), chunk):
        part = pcm[start : start + chunk].astype(np.float32)
        if part.size == 0:
            continue
        result = session.push(AudioFrame(seq=seq, pcm=part, sample_rate=sr))
        seq += 1
        if result.started:
            break

    assert result is not None
    assert result.started
    assert result.detected_note is not None
    assert result.detected_note.measure == case["expected_start_note"]["measure"]
    assert session.state == "started"
