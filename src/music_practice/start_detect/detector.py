"""Batch and in-memory start-point detection using narrow-window pitch DTW."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from music2seq.features.pitch_extractor import (
    PitchSequence,
    clip_to_pitch_sequence,
    wav_to_pitch_sequence,
)
from music2seq.features.preprocess import pitch_preprocess_config
from music2seq.matcher.global_match import GlobalMatchConfig, match_global_sequences
from music2seq.template.store import TemplatePackage, load_template
from music2seq.types import NoteEvent

from music_practice.models import Score
from music_practice.pitch.convert import hz_to_pitch_name, midi_to_hz
from music_practice.score.resolver import notes_in_measure
from music_practice.start_detect.context import DetectedNote, StartDetectContext, StartDetectResult
from music_practice.start_detect.template_window import (
    load_package_note_events,
    resolve_template_sec_from_package,
    slice_pitch_window,
)
from music_practice.types import StartNoteRef


def _make_match_config(package: TemplatePackage) -> GlobalMatchConfig:
    pre_cfg = package.preprocess_config or pitch_preprocess_config()
    pitch_cfg = package.pitch_feature
    return GlobalMatchConfig(
        preprocess=pre_cfg,
        pitch=pitch_cfg,
        cost_metric="cosine",
        cost_margin=0.05,
        normalize="z_score",
        earliest_tiebreak=True,
    )


def _nearest_note(events: list[NoteEvent], template_sec: float) -> NoteEvent | None:
    if not events:
        return None
    covering = [
        event
        for event in events
        if event.start_sec <= template_sec < event.end_sec
    ]
    if covering:
        return min(covering, key=lambda event: (event.end_sec - event.start_sec, event.note_id))
    return min(events, key=lambda event: abs(event.start_sec - template_sec))


def _note_index_in_measure(score: Score, measure: int, beat: float) -> int:
    items = notes_in_measure(score, measure)
    for index, note in enumerate(items, start=1):
        if abs(note.beat - beat) < 0.01:
            return index
    if not items:
        return 0
    nearest = min(items, key=lambda note: abs(note.beat - beat))
    for index, note in enumerate(items, start=1):
        if note is nearest:
            return index
    return 0


def _resolve_template_wav(package: TemplatePackage) -> Path:
    source = Path(package.meta.source_wav)
    if not source.is_absolute():
        if package.root is None:
            raise FileNotFoundError(
                f"模板源音频为相对路径但缺少 package.root: {source}"
            )
        source = (package.root / source).resolve()
    if not source.exists():
        raise FileNotFoundError(f"模板源音频不存在: {source}")
    return source


def _anchor_note_event(events: list[NoteEvent], ref: StartNoteRef) -> NoteEvent:
    items = [event for event in events if event.measure == ref.measure]
    items.sort(key=lambda event: (event.beat, event.start_sec))
    if ref.note_index_in_measure < 1 or ref.note_index_in_measure > len(items):
        raise ValueError(f"measure {ref.measure} 锚点索引无效: {ref.note_index_in_measure}")
    return items[ref.note_index_in_measure - 1]


def _map_detected_note(
    *,
    score: Score,
    events: list[NoteEvent],
    start_note: StartNoteRef,
    template_sec: float,
    global_start_sec: float,
    anchor_snap_sec: float = 0.15,
) -> DetectedNote | None:
    anchor_event = _anchor_note_event(events, start_note)
    anchor_delta = abs(global_start_sec - template_sec)
    if anchor_delta <= anchor_snap_sec:
        note_event = anchor_event
    else:
        note_event = _nearest_note(events, global_start_sec)
        if note_event is None:
            return None

    pitch_name = None
    if note_event.pitch_midi is not None:
        pitch_name = hz_to_pitch_name(midi_to_hz(float(note_event.pitch_midi)))

    return DetectedNote(
        measure=note_event.measure,
        beat=note_event.beat,
        note_index_in_measure=_note_index_in_measure(score, note_event.measure, note_event.beat),
        pitch=pitch_name,
        pitch_midi=note_event.pitch_midi,
        onset=max(0.0, global_start_sec - template_sec),
    )


def _match_against_local(
    *,
    score: Score,
    start_note: StartNoteRef,
    note_events: list[NoteEvent],
    local_template: PitchSequence,
    offset_center_frame: int,
    query_seq: PitchSequence,
    cfg: GlobalMatchConfig,
    template_sec: float,
    ctx: StartDetectContext,
    template_id: str,
    extra: dict | None = None,
) -> StartDetectResult:
    match = match_global_sequences(local_template, query_seq, cfg)
    offset_sec = cfg.pitch.frame_to_sec(offset_center_frame)
    global_start_sec = offset_sec + match.start_sec
    anchor_delta = abs(global_start_sec - template_sec)
    detected_note = _map_detected_note(
        score=score,
        events=note_events,
        start_note=start_note,
        template_sec=template_sec,
        global_start_sec=global_start_sec,
    )
    started = (
        query_seq.duration_sec >= ctx.min_query_sec
        and match.score >= ctx.score_threshold
        and anchor_delta <= ctx.anchor_tolerance_sec
    )
    payload = {
        "template_id": template_id,
        "normalized_cost": match.normalized_cost,
        "window_after_sec": ctx.window_after_sec,
        "anchor_delta_sec": anchor_delta,
    }
    if extra:
        payload.update(extra)
    return StartDetectResult(
        start_note=start_note,
        started=started,
        timed_out=False,
        wait_timeout_sec=ctx.wait_timeout_sec,
        detected_note=detected_note,
        confidence=match.score,
        template_sec=template_sec,
        detected_template_sec=global_start_sec,
        query_duration_sec=query_seq.duration_sec,
        extra=payload,
    )


def prepare_template_window(
    package: TemplatePackage,
    start_note: StartNoteRef,
    *,
    context: StartDetectContext | None = None,
) -> tuple[float, list[NoteEvent], GlobalMatchConfig, PitchSequence, int]:
    """Resolve T0 and cache the narrow template pitch window."""
    ctx = context or StartDetectContext()
    note_events = load_package_note_events(package)
    template_sec = resolve_template_sec_from_package(package, start_note)
    cfg = _make_match_config(package)
    template_wav = _resolve_template_wav(package)
    template_full = wav_to_pitch_sequence(
        template_wav,
        preprocess_config=cfg.preprocess,
        pitch_config=cfg.pitch,
    )
    window_end = min(template_full.duration_sec, template_sec + ctx.window_after_sec)
    local_template, offset_center_frame = slice_pitch_window(
        template_full,
        template_sec,
        window_end,
    )
    return template_sec, note_events, cfg, local_template, offset_center_frame


def detect_start_audio(
    score: Score,
    *,
    start_note: StartNoteRef,
    query_pcm: np.ndarray,
    sample_rate: int,
    template_sec: float,
    note_events: list[NoteEvent],
    cfg: GlobalMatchConfig,
    local_template: PitchSequence,
    offset_center_frame: int,
    template_id: str,
    context: StartDetectContext | None = None,
) -> StartDetectResult:
    """Run narrow-window DTW on an in-memory PCM clip (no WAV required)."""
    ctx = context or StartDetectContext()
    pcm = np.asarray(query_pcm, dtype=np.float32).reshape(-1)
    if pcm.size == 0:
        return StartDetectResult(
            start_note=start_note,
            started=False,
            wait_timeout_sec=ctx.wait_timeout_sec,
            template_sec=template_sec,
            query_duration_sec=0.0,
            extra={"template_id": template_id, "reason": "empty_pcm"},
        )

    query_seq = clip_to_pitch_sequence(
        pcm,
        sample_rate,
        preprocess_config=cfg.preprocess,
        pitch_config=cfg.pitch,
    )
    return _match_against_local(
        score=score,
        start_note=start_note,
        note_events=note_events,
        local_template=local_template,
        offset_center_frame=offset_center_frame,
        query_seq=query_seq,
        cfg=cfg,
        template_sec=template_sec,
        ctx=ctx,
        template_id=template_id,
    )


def detect_start(
    score: Score,
    *,
    template_id: str,
    start_note: StartNoteRef,
    query_wav: str | Path,
    templates_dir: str | Path,
    context: StartDetectContext | None = None,
) -> StartDetectResult:
    """Detect whether the user started playing at the selected anchor note (WAV)."""
    ctx = context or StartDetectContext()
    query_path = Path(query_wav)
    if not query_path.exists():
        raise FileNotFoundError(f"查询音频不存在: {query_path}")

    package = load_template(template_id, templates_dir=Path(templates_dir))
    template_sec, note_events, cfg, local_template, offset_center_frame = prepare_template_window(
        package,
        start_note,
        context=ctx,
    )
    query_seq = wav_to_pitch_sequence(
        query_path,
        preprocess_config=cfg.preprocess,
        pitch_config=cfg.pitch,
    )
    return _match_against_local(
        score=score,
        start_note=start_note,
        note_events=note_events,
        local_template=local_template,
        offset_center_frame=offset_center_frame,
        query_seq=query_seq,
        cfg=cfg,
        template_sec=template_sec,
        ctx=ctx,
        template_id=template_id,
        extra={"query_path": str(query_path.resolve())},
    )
