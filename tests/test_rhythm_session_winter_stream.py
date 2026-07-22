"""Stream RhythmSession on winter template window vs batch evaluate_rhythm."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from music_practice.rhythm.judge import ExpectedNote
from music_practice.rhythm.pipeline import evaluate_rhythm
from music_practice.rhythm.session import RhythmSession
from music_practice.start_detect.frame import AudioFrame

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "rhythm_template" / "winter_1973"
LABEL_PATH = FIXTURE / "label.json"
# Match onset analysis hop @ tempo 60 (frame_size=1024).
FRAME_SAMPLES = 1024


@pytest.fixture(scope="module")
def winter_label() -> dict:
    if not LABEL_PATH.exists():
        pytest.skip("winter rhythm fixture missing; run eval_rhythm_template_winter.py --rebuild")
    return json.loads(LABEL_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def winter_audio(winter_label: dict) -> tuple[np.ndarray, int]:
    wav = FIXTURE / winter_label["query"]["wav"]
    audio, sr = sf.read(str(wav), always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    return np.asarray(audio, dtype=np.float32), int(sr)


def _expected(label: dict) -> list[ExpectedNote]:
    return [
        ExpectedNote(
            onset_sec=float(n["onset_sec"]),
            duration_sec=float(n["duration_sec"]),
            pitch_midi=float(n["pitch_midi"]),
            measure=int(n["measure"]),
            note_index_in_measure=int(n["note_index_in_measure"]),
        )
        for n in label["expected_notes"]
    ]


def _iter_frames(audio: np.ndarray, sr: int, frame_samples: int):
    seq = 0
    t0 = 0.0
    for i0 in range(0, len(audio), frame_samples):
        chunk = audio[i0 : i0 + frame_samples]
        if chunk.size == 0:
            break
        yield AudioFrame(seq=seq, pcm=chunk, sample_rate=sr, t0_sec=t0)
        seq += 1
        t0 += chunk.size / float(sr)


def test_winter_stream_emits_only_on_note_close(winter_label: dict, winter_audio):
    audio, sr = winter_audio
    expected = _expected(winter_label)
    tempo = float(winter_label["tempo_bpm"])
    session = RhythmSession.open(expected, tempo_bpm=tempo, sample_rate=sr)

    none_count = 0
    emitted: list = []
    for frame in _iter_frames(audio, sr, FRAME_SAMPLES):
        seg = session.push(frame)
        if seg is None:
            none_count += 1
        else:
            emitted.append(seg)
            # Drain any extras closed in the same update.
            while True:
                extra = session.poll()
                if extra is None:
                    break
                emitted.append(extra)

    emitted.extend(session.flush())

    assert none_count > 0, "most frames should not return a result"
    assert len(emitted) == len(expected)
    # Streaming should finish notes before/at flush, not all only at the end.
    assert session.emitted_count == len(expected)


def test_winter_stream_matches_batch(winter_label: dict, winter_audio):
    audio, sr = winter_audio
    expected = _expected(winter_label)
    tempo = float(winter_label["tempo_bpm"])

    batch = evaluate_rhythm(expected, tempo_bpm=tempo, audio=audio, sample_rate=sr)

    session = RhythmSession.open(expected, tempo_bpm=tempo, sample_rate=sr)
    streamed: list = []
    none_count = 0
    for frame in _iter_frames(audio, sr, FRAME_SAMPLES):
        seg = session.push(frame)
        if seg is None:
            none_count += 1
        else:
            streamed.append(seg)
        while True:
            extra = session.poll()
            if extra is None:
                break
            streamed.append(extra)

    # Live path should have closed most notes before end-of-stream.
    assert none_count > 0
    assert len(streamed) >= max(1, len(expected) // 2)

    streamed.extend(session.flush())
    assert len(streamed) == len(batch) == len(expected)

    # Streaming product path rates (push/flush emits).
    stream_rhythm_ok = sum(1 for s in streamed if s.rhythm_ok)
    stream_onset_ok = sum(1 for s in streamed if s.onset_ok)
    stream_duration_ok = sum(1 for s in streamed if s.duration_ok)
    assert stream_duration_ok == len(expected)
    assert stream_onset_ok >= 15
    # New product rule: rhythm_ok == duration_ok → expect full pass on template.
    assert stream_rhythm_ok == len(expected)

    # Authoritative end state must match batch.
    final = session.final_segments()
    mismatches = []
    for i, (a, b) in enumerate(zip(final, batch)):
        if (
            a.onset_ok != b.onset_ok
            or a.duration_ok != b.duration_ok
            or a.rhythm_ok != b.rhythm_ok
            or a.timing_result != b.timing_result
        ):
            mismatches.append(
                {
                    "i": i,
                    "stream": (a.onset_ok, a.duration_ok, a.rhythm_ok, a.timing_result),
                    "batch": (b.onset_ok, b.duration_ok, b.rhythm_ok, b.timing_result),
                }
            )
    assert not mismatches, f"stream/batch mismatch: {mismatches}"

    # Live emits should match batch flags too (same detector after stable close).
    live_mismatches = []
    for i, (a, b) in enumerate(zip(streamed, batch)):
        if (
            a.onset_ok != b.onset_ok
            or a.duration_ok != b.duration_ok
            or a.rhythm_ok != b.rhythm_ok
        ):
            live_mismatches.append(i)
    assert not live_mismatches, f"live stream emit mismatch at indices {live_mismatches}"
