"""Template package persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from music_practice.start_match.features.preprocess import PreprocessConfig
from music_practice.start_match.types import (
    FEATURE_KIND_MEL,
    FEATURE_KIND_PITCH,
    FeatureConfig,
    NoteEvent,
    PitchFeatureConfig,
    SCHEMA_VERSION,
    TemplateMeta,
)
from music_practice.start_match.score.store import load_note_events, save_note_events


def project_root() -> Path:
    """Deliver package root (…/music-practice-deliver), not the old deps/ layout."""
    # start_match/template/store.py → parents[4] = deliver root
    return Path(__file__).resolve().parents[4]


def default_templates_dir() -> Path:
    """Fallback templates dir under the deliver package root.

    Prefer passing ``templates_dir`` explicitly from start_detect / callers.
    """
    return project_root() / "templates"


@dataclass
class TemplatePackage:
    meta: TemplateMeta
    mel: np.ndarray | None = None
    mel_coarse: np.ndarray | None = None
    pitch: np.ndarray | None = None
    pitch_coarse: np.ndarray | None = None
    note_events: list[NoteEvent] | None = None
    score_calibration: dict[str, Any] | None = None
    root: Path | None = None

    @property
    def template_id(self) -> str:
        return self.meta.template_id

    @property
    def feature_kind(self) -> str:
        return self.meta.feature_kind

    @property
    def feature(self) -> FeatureConfig:
        return self.meta.feature_config

    @property
    def pitch_feature(self) -> PitchFeatureConfig:
        return self.meta.pitch_feature_config

    @property
    def preprocess_config(self) -> PreprocessConfig | None:
        if self.meta.preprocess is None:
            return None
        return PreprocessConfig.from_dict(self.meta.preprocess)

    @property
    def duration_sec(self) -> float:
        return self.meta.duration_sec

    @property
    def num_frames(self) -> int:
        if self.feature_kind == FEATURE_KIND_PITCH and self.pitch is not None:
            return int(self.pitch.shape[0])
        if self.mel is not None:
            return int(self.mel.shape[0])
        return self.meta.num_frames

    @property
    def sequence(self) -> np.ndarray:
        if self.feature_kind == FEATURE_KIND_PITCH:
            if self.pitch is None:
                raise ValueError("pitch 模板缺少 pitch 序列")
            return self.pitch
        if self.mel is None:
            raise ValueError("mel 模板缺少 mel 序列")
        return self.mel

    @property
    def sequence_coarse(self) -> np.ndarray | None:
        if self.feature_kind == FEATURE_KIND_PITCH:
            return self.pitch_coarse
        return self.mel_coarse


def template_dir(templates_dir: Path, template_id: str) -> Path:
    return templates_dir / template_id


def load_template(
    template_id: str,
    *,
    templates_dir: Path | None = None,
) -> TemplatePackage:
    root = templates_dir or default_templates_dir()
    pkg_dir = template_dir(root, template_id)
    meta_path = pkg_dir / "meta.json"
    mel_path = pkg_dir / "mel.npy"
    coarse_path = pkg_dir / "mel_coarse.npy"
    pitch_path = pkg_dir / "pitch.npy"
    pitch_coarse_path = pkg_dir / "pitch_coarse.npy"
    note_events_path = pkg_dir / "note_events.json"
    note_events_meta_path = pkg_dir / "note_events_meta.json"

    if not meta_path.exists():
        raise FileNotFoundError(f"模板不存在: {pkg_dir}")

    meta_dict = json.loads(meta_path.read_text(encoding="utf-8"))
    meta = TemplateMeta(**{k: v for k, v in meta_dict.items() if k in TemplateMeta.__dataclass_fields__})
    mel = np.load(mel_path) if mel_path.exists() else None
    mel_coarse = np.load(coarse_path) if coarse_path.exists() else None
    pitch = np.load(pitch_path) if pitch_path.exists() else None
    pitch_coarse = np.load(pitch_coarse_path) if pitch_coarse_path.exists() else None
    note_events = load_note_events(note_events_path) if note_events_path.exists() else None
    score_calibration = None
    if note_events_meta_path.exists():
        meta_note = json.loads(note_events_meta_path.read_text(encoding="utf-8"))
        score_calibration = meta_note.get("calibration")
    return TemplatePackage(
        meta=meta,
        mel=mel,
        mel_coarse=mel_coarse,
        pitch=pitch,
        pitch_coarse=pitch_coarse,
        note_events=note_events,
        score_calibration=score_calibration,
        root=pkg_dir,
    )


def save_template(
    package: TemplatePackage,
    *,
    templates_dir: Path | None = None,
) -> Path:
    root = templates_dir or default_templates_dir()
    pkg_dir = template_dir(root, package.template_id)
    pkg_dir.mkdir(parents=True, exist_ok=True)

    meta_path = pkg_dir / "meta.json"
    meta_path.write_text(
        json.dumps(package.meta.__dict__, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if package.mel is not None:
        np.save(pkg_dir / "mel.npy", package.mel.astype(np.float32))
    if package.mel_coarse is not None:
        np.save(pkg_dir / "mel_coarse.npy", package.mel_coarse.astype(np.float32))
    if package.pitch is not None:
        np.save(pkg_dir / "pitch.npy", package.pitch.astype(np.float32))
    if package.pitch_coarse is not None:
        np.save(pkg_dir / "pitch_coarse.npy", package.pitch_coarse.astype(np.float32))
    if package.note_events is not None:
        save_note_events(pkg_dir / "note_events.json", package.note_events)
    if package.score_calibration is not None:
        (pkg_dir / "note_events_meta.json").write_text(
            json.dumps({"calibration": package.score_calibration}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return pkg_dir


def build_meta(
    *,
    template_id: str,
    source_wav: Path,
    source_sha256: str,
    duration_sec: float,
    num_frames: int,
    feature: FeatureConfig,
    feature_kind: str = FEATURE_KIND_MEL,
    preprocess: PreprocessConfig | None = None,
    pitch_feature: PitchFeatureConfig | None = None,
    score_path: Path | None = None,
    score_sha256: str | None = None,
) -> TemplateMeta:
    return TemplateMeta(
        schema_version=SCHEMA_VERSION,
        template_id=template_id,
        source_wav=str(source_wav),
        source_sha256=source_sha256,
        duration_sec=duration_sec,
        num_frames=num_frames,
        feature=feature.to_dict(),
        created_at=datetime.now(timezone.utc).isoformat(),
        feature_kind=feature_kind,
        preprocess=preprocess.to_dict() if preprocess is not None else None,
        pitch_feature=pitch_feature.to_dict() if pitch_feature is not None else None,
        score_path=str(score_path) if score_path is not None else None,
        score_sha256=score_sha256,
    )
