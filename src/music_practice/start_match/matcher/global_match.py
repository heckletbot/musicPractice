"""Global full-template subsequence matching with pitch features."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np

from music_practice.start_match.features.pitch_extractor import (
    PitchSequence,
    audio_to_pitch_sequence,
    clip_to_pitch_sequence,
    wav_to_pitch_sequence,
)
from music_practice.start_match.features.preprocess import PreprocessConfig, pitch_preprocess_config
from music_practice.start_match.matcher.dtw import (
    subsequence_dtw_global,
    subsequence_dtw_global_topk,
    subsequence_match_rigid,
)
from music_practice.start_match.types import PitchFeatureConfig


def _shared_minmax(template: np.ndarray, query: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    stacked = np.concatenate([template, query], axis=0)
    mn = float(stacked.min())
    mx = float(stacked.max())
    if mx == mn:
        zeros_t = np.zeros_like(template, dtype=np.float32)
        zeros_q = np.zeros_like(query, dtype=np.float32)
        return zeros_t, zeros_q
    scale = mx - mn
    return (
        ((template - mn) / scale).astype(np.float32),
        ((query - mn) / scale).astype(np.float32),
    )


def normalize_pair(
    template: np.ndarray,
    query: np.ndarray,
    *,
    mode: Literal["z_score", "shared_minmax"],
) -> tuple[np.ndarray, np.ndarray]:
    if mode == "shared_minmax":
        return _shared_minmax(template, query)
    from music_practice.start_match.features.extractor import standardize_with_template_stats

    return standardize_with_template_stats(template, query)


@dataclass
class GlobalMatchConfig:
    preprocess: PreprocessConfig = field(default_factory=pitch_preprocess_config)
    pitch: PitchFeatureConfig = field(default_factory=PitchFeatureConfig)
    cost_metric: Literal["l2", "cosine"] = "l2"
    cost_margin: float = 0.05
    normalize: Literal["z_score", "shared_minmax"] = "z_score"
    earliest_tiebreak: bool = True
    tiebreak: Literal["earliest", "min_cost", "min_cost_latest"] | None = None
    dtw_mode: Literal["global", "rigid"] = "global"
    local_refine_sec: float | None = None

    def effective_tiebreak(self) -> Literal["earliest", "min_cost", "min_cost_latest"]:
        if self.tiebreak is not None:
            return self.tiebreak
        return "earliest" if self.earliest_tiebreak else "min_cost"

    def to_dict(self) -> dict[str, Any]:
        return {
            "preprocess": self.preprocess.to_dict(),
            "pitch": self.pitch.to_dict(),
            "cost_metric": self.cost_metric,
            "cost_margin": self.cost_margin,
            "normalize": self.normalize,
            "earliest_tiebreak": self.earliest_tiebreak,
            "tiebreak": self.tiebreak,
            "dtw_mode": self.dtw_mode,
            "local_refine_sec": self.local_refine_sec,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GlobalMatchConfig:
        return cls(
            preprocess=PreprocessConfig.from_dict(data.get("preprocess", {})),
            pitch=PitchFeatureConfig.from_dict(data.get("pitch", {})),
            cost_metric=data.get("cost_metric", "l2"),
            cost_margin=float(data.get("cost_margin", 0.05)),
            normalize=data.get("normalize", "z_score"),
            earliest_tiebreak=bool(data.get("earliest_tiebreak", True)),
            tiebreak=data.get("tiebreak"),
            dtw_mode=data.get("dtw_mode", "global"),
            local_refine_sec=data.get("local_refine_sec"),
        )

    def params_hash(self) -> str:
        import hashlib
        import json

        payload = json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode()).hexdigest()[:12]


@dataclass
class GlobalMatchResult:
    start_sec: float
    end_sec: float
    start_frame: int
    end_frame: int
    start_center_frame: int
    end_center_frame: int
    normalized_cost: float
    score: float
    query_duration_sec: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _cost_to_score(normalized_cost: float) -> float:
    return float(1.0 / (1.0 + normalized_cost))


def match_global_sequences(
    template_seq: PitchSequence,
    query_seq: PitchSequence,
    config: GlobalMatchConfig,
) -> GlobalMatchResult:
    template_std, query_std = normalize_pair(
        template_seq.features,
        query_seq.features,
        mode=config.normalize,
    )
    if config.dtw_mode == "rigid":
        cost, start_ctx, end_ctx = subsequence_match_rigid(
            template_std,
            query_std,
            cost_metric=config.cost_metric,
            tiebreak=config.effective_tiebreak(),
        )
    else:
        cost, start_ctx, end_ctx = subsequence_dtw_global(
            template_std,
            query_std,
            cost_metric=config.cost_metric,
            cost_margin=config.cost_margin,
            tiebreak=config.effective_tiebreak(),
        )
    pitch_cfg = config.pitch
    if config.local_refine_sec and config.dtw_mode == "global":
        m = query_std.shape[0]
        refine_f = max(
            1,
            int(round(config.local_refine_sec * pitch_cfg.sample_rate / pitch_cfg.hop_length)),
        )
        lo = max(0, start_ctx - refine_f)
        hi = min(template_std.shape[0] - m, start_ctx + refine_f)
        sub_t = template_std[lo : hi + m]
        cost, st2, en2 = subsequence_match_rigid(
            sub_t,
            query_std,
            cost_metric=config.cost_metric,
            tiebreak="min_cost_latest",
        )
        start_ctx = lo + st2
        end_ctx = lo + en2
    start_center = int(template_seq.center_frames[start_ctx])
    end_center = int(template_seq.center_frames[end_ctx])
    return GlobalMatchResult(
        start_sec=pitch_cfg.frame_to_sec(start_center),
        end_sec=pitch_cfg.frame_to_sec(end_center),
        start_frame=start_ctx,
        end_frame=end_ctx,
        start_center_frame=start_center,
        end_center_frame=end_center,
        normalized_cost=cost,
        score=_cost_to_score(cost),
        query_duration_sec=query_seq.duration_sec,
    )


def match_global_sequences_topk(
    template_seq: PitchSequence,
    query_seq: PitchSequence,
    config: GlobalMatchConfig,
    *,
    top_k: int = 5,
    min_separation_sec: float | None = None,
) -> list[GlobalMatchResult]:
    template_std, query_std = normalize_pair(
        template_seq.features,
        query_seq.features,
        mode=config.normalize,
    )
    separation_frames = None
    if min_separation_sec is not None:
        separation_frames = max(
            1,
            int(round(min_separation_sec * config.pitch.sample_rate / config.pitch.hop_length)),
        )
    if config.dtw_mode == "rigid":
        pairs = [
            subsequence_match_rigid(
                template_std,
                query_std,
                cost_metric=config.cost_metric,
                tiebreak=config.effective_tiebreak(),
            )
        ]
    else:
        pairs = subsequence_dtw_global_topk(
            template_std,
            query_std,
            top_k=top_k,
            cost_metric=config.cost_metric,
            min_separation_frames=separation_frames,
        )

    results: list[GlobalMatchResult] = []
    for cost, start_ctx, end_ctx in pairs[:top_k]:
        start_center = int(template_seq.center_frames[start_ctx])
        end_center = int(template_seq.center_frames[end_ctx])
        results.append(
            GlobalMatchResult(
                start_sec=config.pitch.frame_to_sec(start_center),
                end_sec=config.pitch.frame_to_sec(end_center),
                start_frame=start_ctx,
                end_frame=end_ctx,
                start_center_frame=start_center,
                end_center_frame=end_center,
                normalized_cost=cost,
                score=_cost_to_score(cost),
                query_duration_sec=query_seq.duration_sec,
            )
        )
    return results


def match_global_wav(
    template_wav: str | Path,
    query_wav: str | Path,
    config: GlobalMatchConfig | None = None,
) -> GlobalMatchResult:
    cfg = config or GlobalMatchConfig()
    template_seq = wav_to_pitch_sequence(
        Path(template_wav),
        preprocess_config=cfg.preprocess,
        pitch_config=cfg.pitch,
    )
    query_seq = wav_to_pitch_sequence(
        Path(query_wav),
        preprocess_config=cfg.preprocess,
        pitch_config=cfg.pitch,
    )
    return match_global_sequences(template_seq, query_seq, cfg)


def match_global_audio(
    template_audio: np.ndarray,
    query_audio: np.ndarray,
    sample_rate: int,
    config: GlobalMatchConfig | None = None,
) -> GlobalMatchResult:
    cfg = config or GlobalMatchConfig()
    template_seq = clip_to_pitch_sequence(
        template_audio,
        sample_rate,
        preprocess_config=cfg.preprocess,
        pitch_config=cfg.pitch,
    )
    query_seq = clip_to_pitch_sequence(
        query_audio,
        sample_rate,
        preprocess_config=cfg.preprocess,
        pitch_config=cfg.pitch,
    )
    return match_global_sequences(template_seq, query_seq, cfg)
