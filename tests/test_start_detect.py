from __future__ import annotations

import json

import pytest

from music_practice.score.store import load_score
from music_practice.start_detect import StartDetectContext, detect_start
from music_practice.types import StartNoteRef

from conftest import START_DETECT_FIXTURES

MANIFEST_PATH = START_DETECT_FIXTURES / "manifest.json"

# Deliverable keeps only cases that passed verification (exclude winter_1973).
_DELIVER_PIECE_IDS = ("meili_flute", "viktor_tale")


@pytest.fixture(scope="module")
def start_detect_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        pytest.skip("start_detect manifest missing")
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def start_detect_context() -> StartDetectContext:
    return StartDetectContext(
        window_after_sec=3.0,
        score_threshold=0.35,
        min_query_sec=1.0,
        max_query_sec=2.0,
    )


def _piece_lookup(manifest: dict) -> dict[str, dict]:
    return {piece["piece_id"]: piece for piece in manifest["pieces"]}


@pytest.mark.parametrize("case_index", list(range(10)))
def test_start_detect_meili_cases(
    start_detect_manifest: dict,
    start_detect_context: StartDetectContext,
    case_index: int,
):
    _run_manifest_cases_for_piece(start_detect_manifest, start_detect_context, "meili_flute", case_index)


@pytest.mark.parametrize("case_index", list(range(10)))
def test_start_detect_viktor_cases(
    start_detect_manifest: dict,
    start_detect_context: StartDetectContext,
    case_index: int,
):
    _run_manifest_cases_for_piece(start_detect_manifest, start_detect_context, "viktor_tale", case_index)


def _run_manifest_cases_for_piece(
    manifest: dict,
    context: StartDetectContext,
    piece_id: str,
    case_index: int,
) -> None:
    piece = _piece_lookup(manifest)[piece_id]
    case = piece["cases"][case_index]
    score = load_score(piece["score_id"], scores_dir=START_DETECT_FIXTURES / "scores")
    ref = StartNoteRef(
        measure=case["expected_start_note"]["measure"],
        note_index_in_measure=case["expected_start_note"]["note_index_in_measure"],
    )
    result = detect_start(
        score,
        template_id=piece["template_id"],
        start_note=ref,
        query_wav=START_DETECT_FIXTURES / case["query_wav"],
        templates_dir=START_DETECT_FIXTURES / "templates",
        context=context,
    )

    assert result.started, (
        f"{case['case_id']}: expected started, "
        f"score={result.confidence:.3f}, query={result.query_duration_sec:.2f}s"
    )
    assert result.detected_note is not None
    assert result.detected_note.measure == case["expected_start_note"]["measure"]
    assert result.detected_note.note_index_in_measure == case["expected_start_note"]["note_index_in_measure"]
    assert result.confidence >= context.score_threshold
    assert abs(result.template_sec - case["template_sec"]) < 0.01


def test_start_detect_summary(start_detect_manifest: dict, start_detect_context: StartDetectContext):
    """Hit rate across deliverable pieces only (meili + viktor = 20 cases)."""
    cases = [
        c for c in start_detect_manifest["cases"] if c["piece_id"] in _DELIVER_PIECE_IDS
    ]
    hits = 0
    failures: list[str] = []

    for case in cases:
        piece = _piece_lookup(start_detect_manifest)[case["piece_id"]]
        score = load_score(piece["score_id"], scores_dir=START_DETECT_FIXTURES / "scores")
        ref = StartNoteRef(
            measure=case["expected_start_note"]["measure"],
            note_index_in_measure=case["expected_start_note"]["note_index_in_measure"],
        )
        result = detect_start(
            score,
            template_id=piece["template_id"],
            start_note=ref,
            query_wav=START_DETECT_FIXTURES / case["query_wav"],
            templates_dir=START_DETECT_FIXTURES / "templates",
            context=start_detect_context,
        )
        ok = (
            result.started
            and result.detected_note is not None
            and result.detected_note.measure == case["expected_start_note"]["measure"]
            and result.detected_note.note_index_in_measure == case["expected_start_note"]["note_index_in_measure"]
        )
        if ok:
            hits += 1
        else:
            failures.append(
                f"{case['case_id']}: started={result.started}, "
                f"conf={result.confidence:.3f}, "
                f"det=({getattr(result.detected_note, 'measure', None)}, "
                f"{getattr(result.detected_note, 'note_index_in_measure', None)})"
            )

    total = len(cases)
    assert hits == total, f"hit_rate={hits}/{total}, failures={failures[:5]}"
