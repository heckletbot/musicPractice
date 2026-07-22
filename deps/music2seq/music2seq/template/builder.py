"""Build template packages from reference audio."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import numpy as np

from music2seq.features.extractor import wav_to_mel
from music2seq.features.pitch_extractor import wav_to_pitch
from music2seq.features.preprocess import PreprocessConfig, pitch_preprocess_config
from music2seq.score.calibrate import calibrate_note_events_to_template
from music2seq.score.parser import parse_musicxml
from music2seq.template.store import TemplatePackage, build_meta, save_template, template_dir
from music2seq.types import (
    FEATURE_KIND_MEL,
    FEATURE_KIND_PITCH,
    FeatureConfig,
    PitchFeatureConfig,
    validate_template_duration,
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_coarse_sequence(sequence: np.ndarray, pool: int = 4) -> np.ndarray:
    """Average-pool frames for coarse search."""
    length = sequence.shape[0]
    usable = (length // pool) * pool
    if usable < pool:
        return sequence.copy()
    trimmed = sequence[:usable]
    return trimmed.reshape(usable // pool, pool, sequence.shape[1]).mean(axis=1).astype(np.float32)


def build_template(
    source_wav: str | Path,
    *,
    template_id: str | None = None,
    templates_dir: Path | None = None,
    feature: FeatureConfig | None = None,
    pitch_feature: PitchFeatureConfig | None = None,
    preprocess: PreprocessConfig | None = None,
    score_path: str | Path | None = None,
    feature_kind: str = FEATURE_KIND_MEL,
    overwrite: bool = False,
    validate_duration: bool = True,
) -> str:
    path = Path(source_wav)
    if not path.exists():
        raise FileNotFoundError(f"源音频不存在: {path}")

    if feature_kind not in (FEATURE_KIND_MEL, FEATURE_KIND_PITCH):
        raise ValueError(f"不支持的 feature_kind: {feature_kind}")

    score = Path(score_path) if score_path is not None else None
    note_events = None
    score_sha256 = None
    score_calibration = None
    if score is not None:
        if not score.exists():
            raise FileNotFoundError(f"谱面文件不存在: {score}")
        score_sha256 = _sha256_file(score)

    tid = template_id or uuid.uuid4().hex

    from music2seq.template.store import default_templates_dir

    root = templates_dir or default_templates_dir()
    out_dir = template_dir(root, tid)
    if out_dir.exists() and not overwrite:
        raise FileExistsError(f"模板已存在: {out_dir}（使用 overwrite=True 覆盖）")

    if feature_kind == FEATURE_KIND_MEL:
        config = feature or FeatureConfig()
        mel, duration_sec, _ = wav_to_mel(path, config)
        if validate_duration:
            validate_template_duration(duration_sec)
        if score is not None:
            raw_events = parse_musicxml(score)
            note_events, score_calibration = calibrate_note_events_to_template(raw_events, duration_sec)
        package = TemplatePackage(
            meta=build_meta(
                template_id=tid,
                source_wav=path.resolve(),
                source_sha256=_sha256_file(path),
                duration_sec=duration_sec,
                num_frames=int(mel.shape[0]),
                feature=config,
                feature_kind=FEATURE_KIND_MEL,
                score_path=score.resolve() if score is not None else None,
                score_sha256=score_sha256,
            ),
            mel=mel,
            mel_coarse=_build_coarse_sequence(mel),
            note_events=note_events,
            score_calibration=score_calibration.to_dict() if score_calibration is not None else None,
        )
    else:
        pitch_cfg = pitch_feature or PitchFeatureConfig()
        pre_cfg = preprocess or pitch_preprocess_config()
        feature_cfg = feature or FeatureConfig(
            sample_rate=pitch_cfg.sample_rate,
            hop_length=pitch_cfg.hop_length,
        )
        pitch, duration_sec, _ = wav_to_pitch(
            path,
            preprocess_config=pre_cfg,
            pitch_config=pitch_cfg,
        )
        if validate_duration:
            validate_template_duration(duration_sec)
        if score is not None:
            raw_events = parse_musicxml(score)
            note_events, score_calibration = calibrate_note_events_to_template(raw_events, duration_sec)
        package = TemplatePackage(
            meta=build_meta(
                template_id=tid,
                source_wav=path.resolve(),
                source_sha256=_sha256_file(path),
                duration_sec=duration_sec,
                num_frames=int(pitch.shape[0]),
                feature=feature_cfg,
                feature_kind=FEATURE_KIND_PITCH,
                preprocess=pre_cfg,
                pitch_feature=pitch_cfg,
                score_path=score.resolve() if score is not None else None,
                score_sha256=score_sha256,
            ),
            pitch=pitch,
            pitch_coarse=_build_coarse_sequence(pitch),
            note_events=note_events,
            score_calibration=score_calibration.to_dict() if score_calibration is not None else None,
        )

    save_template(package, templates_dir=root)
    return tid
