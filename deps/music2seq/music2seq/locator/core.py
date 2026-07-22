"""Score-aware query localization."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from music2seq.features.pitch_extractor import PitchSequence, wav_to_pitch_sequence
from music2seq.features.preprocess import pitch_preprocess_config
from music2seq.matcher.global_match import (
    GlobalMatchConfig,
    GlobalMatchResult,
    match_global_sequences_topk,
)
from music2seq.template.store import TemplatePackage, load_template
from music2seq.types import LocateCandidate, LocateContext, LocateResult, NoteEvent, validate_query_duration


def _slice_pitch_sequence(seq: PitchSequence, start_sec: float, end_sec: float) -> tuple[PitchSequence, int]:
    start_frame = int(round(start_sec * seq.sample_rate / seq.hop_length))
    end_frame = int(round(end_sec * seq.sample_rate / seq.hop_length))
    centers = seq.center_frames
    mask = (centers >= start_frame) & (centers <= end_frame)
    indices = np.flatnonzero(mask)
    if indices.size == 0:
        raise ValueError("局部搜索窗口内没有可用特征帧")
    lo = int(indices[0])
    hi = int(indices[-1]) + 1
    return (
        PitchSequence(
            features=seq.features[lo:hi],
            center_frames=seq.center_frames[lo:hi] - seq.center_frames[lo],
            sample_rate=seq.sample_rate,
            hop_length=seq.hop_length,
            duration_sec=(seq.center_frames[hi - 1] - seq.center_frames[lo]) * seq.hop_length / seq.sample_rate,
        ),
        int(seq.center_frames[lo]),
    )


def _nearest_note(events: list[NoteEvent], template_sec: float) -> NoteEvent | None:
    if not events:
        return None
    covering = [event for event in events if event.start_sec <= template_sec <= event.end_sec]
    if covering:
        return min(covering, key=lambda event: (event.end_sec - event.start_sec, event.note_id))
    return min(events, key=lambda event: abs(event.start_sec - template_sec))


def _to_candidate(result: GlobalMatchResult, events: list[NoteEvent], rank: int) -> LocateCandidate:
    note = _nearest_note(events, result.start_sec)
    return LocateCandidate(
        start_sec=result.start_sec,
        end_sec=result.end_sec,
        score=result.score,
        rank=rank,
        note_id=note.note_id if note is not None else None,
        measure=note.measure if note is not None else None,
        beat=note.beat if note is not None else None,
        pitch_midi=note.pitch_midi if note is not None else None,
    )


def _make_config(package: TemplatePackage, global_config: GlobalMatchConfig | None) -> GlobalMatchConfig:
    pre_cfg = package.preprocess_config or pitch_preprocess_config()
    pitch_cfg = package.pitch_feature
    cfg = global_config or GlobalMatchConfig(preprocess=pre_cfg, pitch=pitch_cfg)
    return GlobalMatchConfig(
        preprocess=pre_cfg,
        pitch=pitch_cfg,
        cost_metric=cfg.cost_metric,
        cost_margin=cfg.cost_margin,
        normalize=cfg.normalize,
        earliest_tiebreak=cfg.earliest_tiebreak,
        tiebreak=cfg.tiebreak,
        dtw_mode=cfg.dtw_mode,
        local_refine_sec=cfg.local_refine_sec,
    )


def _context_center(context: LocateContext, query_timestamp_sec: float | None) -> float | None:
    if context.last_template_sec is None:
        return None
    center = context.last_template_sec
    if query_timestamp_sec is not None and context.last_timestamp_sec is not None:
        center += max(0.0, query_timestamp_sec - context.last_timestamp_sec)
    return center


def locate_against_template(
    package: TemplatePackage,
    query_wav: str | Path,
    *,
    context: LocateContext | None = None,
    query_timestamp_sec: float | None = None,
    top_k: int = 5,
    min_separation_sec: float = 3.0,
    ambiguity_score_margin: float = 0.03,
    low_score_threshold: float = 0.35,
    global_config: GlobalMatchConfig | None = None,
) -> LocateResult:
    started = time.perf_counter()
    query_path = Path(query_wav)
    if not query_path.exists():
        raise FileNotFoundError(f"查询音频不存在: {query_path}")
    if not package.note_events:
        raise ValueError("模板包缺少 note_events.json，请使用 score_path 重新构建模板")
    template_wav = Path(package.meta.source_wav)
    if not template_wav.exists():
        raise FileNotFoundError(f"模板源音频不存在: {template_wav}")

    cfg = _make_config(package, global_config)
    template_seq = wav_to_pitch_sequence(template_wav, preprocess_config=cfg.preprocess, pitch_config=cfg.pitch)
    query_seq = wav_to_pitch_sequence(query_path, preprocess_config=cfg.preprocess, pitch_config=cfg.pitch)
    validate_query_duration(query_seq.duration_sec)

    context_used = False
    warning = None
    results: list[GlobalMatchResult] = []
    center = _context_center(context, query_timestamp_sec) if context is not None else None
    if center is not None:
        half = max(query_seq.duration_sec, context.expected_window_sec) / 2.0
        try:
            local_seq, offset_center_frame = _slice_pitch_sequence(
                template_seq,
                max(0.0, center - half),
                min(package.duration_sec, center + half),
            )
            local_results = match_global_sequences_topk(
                local_seq,
                query_seq,
                cfg,
                top_k=top_k,
                min_separation_sec=min_separation_sec,
            )
            for item in local_results:
                offset_sec = cfg.pitch.frame_to_sec(offset_center_frame)
                item.start_sec += offset_sec
                item.end_sec += offset_sec
                item.start_center_frame += offset_center_frame
                item.end_center_frame += offset_center_frame
            if local_results and local_results[0].score >= low_score_threshold:
                results = local_results
                context_used = True
        except ValueError as exc:
            warning = str(exc)

    if not results:
        results = match_global_sequences_topk(
            template_seq,
            query_seq,
            cfg,
            top_k=top_k,
            min_separation_sec=min_separation_sec,
        )

    candidates = [_to_candidate(item, package.note_events, idx + 1) for idx, item in enumerate(results)]
    best = candidates[0] if candidates else None
    ambiguous = False
    confidence = 0.0
    if best is not None:
        confidence = best.score
        if len(candidates) > 1 and (best.score - candidates[1].score) <= ambiguity_score_margin:
            ambiguous = True
            confidence = max(0.0, best.score - candidates[1].score)
        if best.score < low_score_threshold:
            warning = warning or f"定位置信度偏低 (score={best.score:.3f})"

    return LocateResult(
        template_id=package.template_id,
        best=best,
        top_k=candidates,
        ambiguous=ambiguous,
        confidence=confidence,
        context_used=context_used,
        query_duration_sec=query_seq.duration_sec,
        query_path=str(query_path.resolve()),
        warning=warning,
        runtime_sec=time.perf_counter() - started,
        extra={
            "params_hash": cfg.params_hash(),
            "top_k": top_k,
            "min_separation_sec": min_separation_sec,
            "query_timestamp_sec": query_timestamp_sec,
        },
    )


def locate_query(
    template_id: str,
    query_wav: str | Path,
    *,
    templates_dir: Path | None = None,
    context: LocateContext | None = None,
    query_timestamp_sec: float | None = None,
    top_k: int = 5,
) -> LocateResult:
    package = load_template(template_id, templates_dir=templates_dir)
    return locate_against_template(
        package,
        query_wav,
        context=context,
        query_timestamp_sec=query_timestamp_sec,
        top_k=top_k,
    )
