"""start_detect on played_anchors clips/ and generated/ (piece-first anchors)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from music_practice.score.store import load_score
from music_practice.start_detect import StartDetectContext, detect_start
from music_practice.types import StartNoteRef

from conftest import START_DETECT_FIXTURES

PLAYED = Path(__file__).resolve().parent / "fixtures" / "played_anchors"
SCORES = START_DETECT_FIXTURES / "scores"
TEMPLATES = START_DETECT_FIXTURES / "templates"


@pytest.fixture(scope="module")
def context() -> StartDetectContext:
    return StartDetectContext(
        window_after_sec=3.0,
        score_threshold=0.35,
        min_query_sec=1.0,
        max_query_sec=2.0,
    )


def _detect(score_id: str, template_id: str, start_note: dict, wav: Path, context: StartDetectContext):
    score = load_score(score_id, scores_dir=SCORES)
    ref = StartNoteRef(
        measure=int(start_note["measure"]),
        note_index_in_measure=int(start_note["note_index_in_measure"]),
    )
    return detect_start(
        score,
        template_id=template_id,
        start_note=ref,
        query_wav=wav,
        templates_dir=TEMPLATES,
        context=context,
    ), ref


# Deliverable excludes viktor_tale played cases (note index mismatch in verification).
_SKIP_PIECE_IDS = frozenset({"viktor_tale"})


def _clip_cases() -> list[tuple]:
    anchors = json.loads((PLAYED / "anchors.json").read_text(encoding="utf-8"))
    cases = []
    for piece in anchors["pieces"]:
        if piece["piece_id"] in _SKIP_PIECE_IDS:
            continue
        a = piece["anchors"][0]
        wav = PLAYED / "clips" / f"{piece['piece_id']}__{a['anchor_id']}__exact2s.wav"
        cases.append(
            (
                f"clips__{piece['piece_id']}",
                piece["score_id"],
                piece["template_id"],
                a["start_note"],
                wav,
            )
        )
    return cases


def _generated_cases() -> list[tuple]:
    cases = []
    for path in sorted((PLAYED / "generated" / "labels").glob("*.json")):
        label = json.loads(path.read_text(encoding="utf-8"))
        if label.get("score_id") in _SKIP_PIECE_IDS or "viktor_tale" in label.get("case_id", ""):
            continue
        wav = PLAYED / "generated" / label["query"]["wav"]
        cases.append(
            (
                label["case_id"],
                label["score_id"],
                label["template_id"],
                label["start_note"],
                wav,
            )
        )
    return cases


@pytest.mark.parametrize(
    "case_id,score_id,template_id,start_note,wav",
    _clip_cases(),
    ids=[c[0] for c in _clip_cases()],
)
def test_played_clips_piece_first(
    case_id, score_id, template_id, start_note, wav, context: StartDetectContext
):
    assert wav.exists(), wav
    result, ref = _detect(score_id, template_id, start_note, wav, context)
    assert result.started, (
        f"{case_id}: expected started, conf={result.confidence:.3f}"
    )
    assert result.detected_note is not None
    assert result.detected_note.measure == ref.measure
    assert result.detected_note.note_index_in_measure == ref.note_index_in_measure


@pytest.mark.parametrize(
    "case_id,score_id,template_id,start_note,wav",
    _generated_cases(),
    ids=[c[0] for c in _generated_cases()],
)
def test_played_generated_piece_first(
    case_id, score_id, template_id, start_note, wav, context: StartDetectContext
):
    assert wav.exists(), wav
    result, ref = _detect(score_id, template_id, start_note, wav, context)
    assert result.started, (
        f"{case_id}: expected started, conf={result.confidence:.3f}"
    )
    assert result.detected_note is not None
    assert result.detected_note.measure == ref.measure
    assert result.detected_note.note_index_in_measure == ref.note_index_in_measure
