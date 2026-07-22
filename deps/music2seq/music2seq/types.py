"""Shared types, constants, and validation for music2seq."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

QUERY_DURATION_MIN_SEC = 1.0
QUERY_DURATION_MAX_SEC = 5.0
TEMPLATE_DURATION_MIN_SEC = 5 * 60
TEMPLATE_DURATION_MAX_SEC = 30 * 60
SCHEMA_VERSION = "1.0"

FEATURE_KIND_MEL = "mel"
FEATURE_KIND_PITCH = "pitch_chroma_cqt"


@dataclass(frozen=True)
class FeatureConfig:
    sample_rate: int = 22050
    n_fft: int = 2048
    hop_length: int = 512
    win_length: int = 2048
    n_mels: int = 128
    fmin: float = 27.5
    fmax: float | None = None
    power_to_db_ref: str = "max"
    normalize_minmax: bool = True

    def frame_to_sec(self, frame_index: int) -> float:
        return frame_index * self.hop_length / self.sample_rate

    def sec_to_frame(self, time_sec: float) -> int:
        return int(round(time_sec * self.sample_rate / self.hop_length))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeatureConfig:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass(frozen=True)
class PitchFeatureConfig:
    sample_rate: int = 22050
    hop_length: int = 512
    n_chroma: int = 12
    smooth_frames: int = 11
    use_delta: bool = True
    context_sec: float = 1.5
    normalize_per_frame: bool = True

    def frame_to_sec(self, frame_index: int) -> float:
        return frame_index * self.hop_length / self.sample_rate

    def sec_to_frame(self, time_sec: float) -> int:
        return int(round(time_sec * self.sample_rate / self.hop_length))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PitchFeatureConfig:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class MatchCandidate:
    start_sec: float
    end_sec: float
    score: float
    rank: int


@dataclass
class MatchResult:
    template_id: str
    start_sec: float
    end_sec: float
    score: float
    query_duration_sec: float
    query_path: str | None = None
    method: str = "subsequence_dtw_mel"
    start_frame: int | None = None
    end_frame: int | None = None
    top_k: list[MatchCandidate] = field(default_factory=list)
    warning: str | None = None
    runtime_sec: float | None = None
    extra: dict[str, Any] | None = None

    @property
    def template_span_sec(self) -> float:
        return self.end_sec - self.start_sec

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["template_span_sec"] = self.template_span_sec
        return data

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


@dataclass(frozen=True)
class NoteEvent:
    note_id: str
    measure: int
    beat: float
    pitch_midi: int | None
    start_sec: float
    end_sec: float
    duration_sec: float
    part_id: str | None = None
    voice: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NoteEvent:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass(frozen=True)
class ScorePosition:
    note_id: str
    measure: int
    beat: float
    template_sec: float
    pitch_midi: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LocateCandidate:
    start_sec: float
    end_sec: float
    score: float
    rank: int
    note_id: str | None = None
    measure: int | None = None
    beat: float | None = None
    pitch_midi: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LocateContext:
    last_note_id: str | None = None
    last_template_sec: float | None = None
    last_timestamp_sec: float | None = None
    expected_window_sec: float = 20.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LocateResult:
    template_id: str
    best: LocateCandidate | None
    top_k: list[LocateCandidate] = field(default_factory=list)
    ambiguous: bool = False
    confidence: float = 0.0
    context_used: bool = False
    query_duration_sec: float | None = None
    query_path: str | None = None
    warning: str | None = None
    runtime_sec: float | None = None
    method: str = "score_note_locator"
    extra: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


@dataclass
class TemplateMeta:
    schema_version: str
    template_id: str
    source_wav: str
    source_sha256: str
    duration_sec: float
    num_frames: int
    feature: dict[str, Any]
    created_at: str
    build_tool_version: str = "0.1.0"
    feature_kind: str = FEATURE_KIND_MEL
    preprocess: dict[str, Any] | None = None
    pitch_feature: dict[str, Any] | None = None
    score_path: str | None = None
    score_sha256: str | None = None

    @property
    def feature_config(self) -> FeatureConfig:
        return FeatureConfig.from_dict(self.feature)

    @property
    def pitch_feature_config(self) -> PitchFeatureConfig:
        if self.pitch_feature is not None:
            return PitchFeatureConfig.from_dict(self.pitch_feature)
        return PitchFeatureConfig(
            sample_rate=self.feature.get("sample_rate", 22050),
            hop_length=self.feature.get("hop_length", 512),
        )


def validate_query_duration(duration_sec: float) -> None:
    if duration_sec < QUERY_DURATION_MIN_SEC or duration_sec > QUERY_DURATION_MAX_SEC:
        raise ValueError(
            f"查询音频时长 {duration_sec:.3f}s 不在合法区间 "
            f"[{QUERY_DURATION_MIN_SEC}, {QUERY_DURATION_MAX_SEC}]s"
        )


def validate_template_duration(duration_sec: float) -> None:
    if duration_sec < TEMPLATE_DURATION_MIN_SEC or duration_sec > TEMPLATE_DURATION_MAX_SEC:
        raise ValueError(
            f"模板音频时长 {duration_sec:.1f}s 不在合法区间 "
            f"[{TEMPLATE_DURATION_MIN_SEC}, {TEMPLATE_DURATION_MAX_SEC}]s"
        )
