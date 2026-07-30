"""Match query audio against a template package."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Literal

import numpy as np

from music_practice.start_match.features.extractor import standardize_with_template_stats, wav_to_mel
from music_practice.start_match.features.pitch_extractor import wav_to_pitch_sequence
from music_practice.start_match.features.preprocess import pitch_preprocess_config
from music_practice.start_match.matcher.dtw import coarse_mel_candidates, subsequence_dtw
from music_practice.start_match.matcher.global_match import GlobalMatchConfig, match_global_sequences
from music_practice.start_match.template.store import TemplatePackage, load_template
from music_practice.start_match.types import (
    FEATURE_KIND_PITCH,
    MatchCandidate,
    MatchResult,
    validate_query_duration,
)


def _cost_to_score(normalized_cost: float) -> float:
    return float(1.0 / (1.0 + normalized_cost))


def _refine_window_frames(query_frames: int, band_ratio: float = 0.35) -> int:
    return max(query_frames * 2, int(query_frames * (1.0 + band_ratio) + 32))


def _coarse_starts(
    template_seq: np.ndarray,
    query_seq: np.ndarray,
    coarse_seq: np.ndarray | None,
    *,
    coarse_stride: int,
    coarse_candidates: int,
) -> list[int]:
    if coarse_seq is not None and coarse_seq.shape[0] >= query_seq.shape[0]:
        pool = max(1, template_seq.shape[0] // max(1, coarse_seq.shape[0]))
        q_coarse_len = max(1, query_seq.shape[0] // pool)
        query_coarse = query_seq[: q_coarse_len * pool].reshape(q_coarse_len, pool, query_seq.shape[1]).mean(axis=1)
        candidates = coarse_mel_candidates(
            coarse_seq,
            query_coarse,
            stride=max(1, coarse_stride // pool),
            top_k=coarse_candidates,
        )
        return [c[0] * pool for c in candidates]

    candidates = coarse_mel_candidates(
        template_seq,
        query_seq,
        stride=coarse_stride,
        top_k=coarse_candidates,
    )
    return [c[0] for c in candidates]


def _match_sequences_coarse(
    package: TemplatePackage,
    template_seq: np.ndarray,
    query_seq: np.ndarray,
    query_duration_sec: float,
    query_path: Path,
    *,
    top_k: int,
    coarse_stride: int,
    coarse_candidates: int,
    dtw_band_ratio: float,
    low_score_threshold: float,
    method: str,
    started: float,
    coarse_seq: np.ndarray | None = None,
) -> MatchResult:
    if query_seq.shape[0] > template_seq.shape[0]:
        raise ValueError("查询序列长度超过模板，无法匹配")

    template_std, query_std = standardize_with_template_stats(template_seq, query_seq)
    coarse = coarse_seq if coarse_seq is not None else package.sequence_coarse
    coarse_starts = _coarse_starts(
        template_std,
        query_std,
        coarse,
        coarse_stride=coarse_stride,
        coarse_candidates=coarse_candidates,
    )
    if not coarse_starts:
        coarse_starts = [0]

    window = _refine_window_frames(query_std.shape[0], band_ratio=0.4)
    ranked: list[tuple[float, int, int, float]] = []

    for coarse_start in coarse_starts:
        start = max(0, coarse_start - window // 4)
        end = min(template_std.shape[0], coarse_start + query_std.shape[0] + window)
        segment = template_std[start:end]
        if segment.shape[0] < query_std.shape[0]:
            continue
        cost, rel_start, rel_end = subsequence_dtw(segment, query_std, band_ratio=dtw_band_ratio)
        abs_start = start + rel_start
        abs_end = start + rel_end
        score = _cost_to_score(cost)
        ranked.append((score, abs_start, abs_end, cost))

    if not ranked:
        raise RuntimeError("未找到有效 DTW 对齐路径")

    ranked.sort(key=lambda row: row[0], reverse=True)
    best_score, best_start, best_end, best_cost = ranked[0]

    warning = None
    if best_score < low_score_threshold:
        warning = f"匹配置信度偏低 (score={best_score:.3f})"

    timing = package.pitch_feature if package.feature_kind == FEATURE_KIND_PITCH else package.feature
    top: list[MatchCandidate] = []
    seen: set[tuple[int, int]] = set()
    for score, s_frame, e_frame, _ in ranked:
        key = (s_frame, e_frame)
        if key in seen:
            continue
        seen.add(key)
        top.append(
            MatchCandidate(
                start_sec=timing.frame_to_sec(s_frame),
                end_sec=timing.frame_to_sec(e_frame),
                score=score,
                rank=len(top) + 1,
            )
        )
        if len(top) >= top_k:
            break

    return MatchResult(
        template_id=package.template_id,
        start_sec=timing.frame_to_sec(best_start),
        end_sec=timing.frame_to_sec(best_end),
        score=best_score,
        query_duration_sec=query_duration_sec,
        query_path=str(query_path.resolve()),
        method=method,
        start_frame=best_start,
        end_frame=best_end,
        top_k=top,
        warning=warning,
        runtime_sec=time.perf_counter() - started,
        extra={"dtw_normalized_cost": best_cost, "coarse_candidates": len(coarse_starts)},
    )


def _match_pitch_global(
    package: TemplatePackage,
    query_path: Path,
    *,
    top_k: int,
    low_score_threshold: float,
    started: float,
    global_config: GlobalMatchConfig | None = None,
) -> MatchResult:
    pre_cfg = package.preprocess_config or pitch_preprocess_config()
    pitch_cfg = package.pitch_feature
    gcfg = global_config or GlobalMatchConfig(preprocess=pre_cfg, pitch=pitch_cfg)
    gcfg = GlobalMatchConfig(
        preprocess=pre_cfg,
        pitch=pitch_cfg,
        cost_metric=gcfg.cost_metric,
        cost_margin=gcfg.cost_margin,
        normalize=gcfg.normalize,
        earliest_tiebreak=gcfg.earliest_tiebreak,
    )

    if package.root is None:
        raise ValueError("模板包缺少 root 路径，无法 global 匹配")
    template_wav = Path(package.meta.source_wav)
    if not template_wav.exists():
        raise FileNotFoundError(f"模板源音频不存在: {template_wav}")

    template_seq = wav_to_pitch_sequence(
        template_wav,
        preprocess_config=gcfg.preprocess,
        pitch_config=gcfg.pitch,
    )
    query_seq = wav_to_pitch_sequence(
        query_path,
        preprocess_config=gcfg.preprocess,
        pitch_config=gcfg.pitch,
    )
    validate_query_duration(query_seq.duration_sec)
    result = match_global_sequences(template_seq, query_seq, gcfg)

    warning = None
    if result.score < low_score_threshold:
        warning = f"匹配置信度偏低 (score={result.score:.3f})"

    return MatchResult(
        template_id=package.template_id,
        start_sec=result.start_sec,
        end_sec=result.end_sec,
        score=result.score,
        query_duration_sec=result.query_duration_sec,
        query_path=str(query_path.resolve()),
        method="subsequence_dtw_pitch_global",
        start_frame=result.start_center_frame,
        end_frame=result.end_center_frame,
        top_k=[
            MatchCandidate(
                start_sec=result.start_sec,
                end_sec=result.end_sec,
                score=result.score,
                rank=1,
            )
        ][:top_k],
        warning=warning,
        runtime_sec=time.perf_counter() - started,
        extra={
            "dtw_normalized_cost": result.normalized_cost,
            "search_mode": "global",
            "params_hash": gcfg.params_hash(),
        },
    )


def match_against_template(
    package: TemplatePackage,
    query_wav: str | Path,
    *,
    top_k: int = 3,
    coarse_stride: int = 8,
    coarse_candidates: int = 24,
    dtw_band_ratio: float = 0.12,
    low_score_threshold: float = 0.35,
    search_mode: Literal["global", "coarse_local"] = "global",
    global_config: GlobalMatchConfig | None = None,
) -> MatchResult:
    started = time.perf_counter()
    query_path = Path(query_wav)
    if not query_path.exists():
        raise FileNotFoundError(f"查询音频不存在: {query_path}")

    if package.feature_kind == FEATURE_KIND_PITCH:
        if search_mode == "global":
            return _match_pitch_global(
                package,
                query_path,
                top_k=top_k,
                low_score_threshold=low_score_threshold,
                started=started,
                global_config=global_config,
            )
        query_seq = wav_to_pitch_sequence(
            query_path,
            preprocess_config=package.preprocess_config or pitch_preprocess_config(),
            pitch_config=package.pitch_feature,
        )
        validate_query_duration(query_seq.duration_sec)
        return _match_sequences_coarse(
            package,
            package.sequence,
            query_seq.features,
            query_seq.duration_sec,
            query_path,
            top_k=top_k,
            coarse_stride=coarse_stride,
            coarse_candidates=coarse_candidates,
            dtw_band_ratio=dtw_band_ratio,
            low_score_threshold=low_score_threshold,
            method="subsequence_dtw_pitch",
            started=started,
        )

    config = package.feature
    query_mel, query_duration_sec, _ = wav_to_mel(query_path, config)
    validate_query_duration(query_duration_sec)
    return _match_sequences_coarse(
        package,
        package.sequence,
        query_mel,
        query_duration_sec,
        query_path,
        top_k=top_k,
        coarse_stride=coarse_stride,
        coarse_candidates=coarse_candidates,
        dtw_band_ratio=dtw_band_ratio,
        low_score_threshold=low_score_threshold,
        method="subsequence_dtw_mel",
        started=started,
    )


def match_query(
    template_id: str,
    query_wav: str | Path,
    *,
    templates_dir: Path | None = None,
    top_k: int = 3,
    dtw_band_ratio: float = 0.12,
    search_mode: Literal["global", "coarse_local"] = "global",
    global_config: GlobalMatchConfig | None = None,
) -> MatchResult:
    package = load_template(template_id, templates_dir=templates_dir)
    return match_against_template(
        package,
        query_wav,
        top_k=top_k,
        dtw_band_ratio=dtw_band_ratio,
        search_mode=search_mode,
        global_config=global_config,
    )
