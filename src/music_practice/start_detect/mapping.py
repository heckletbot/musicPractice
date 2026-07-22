"""Resolve score_id → template_id for start detection."""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_MAP_PATH = Path(__file__).resolve().parents[3] / "data" / "score_template_map.json"


def default_score_template_map_path() -> Path:
    return DEFAULT_MAP_PATH


def load_score_template_map(path: str | Path | None = None) -> dict[str, str]:
    """Return ``{score_id: template_id}`` from a JSON mapping file."""
    map_path = Path(path) if path is not None else default_score_template_map_path()
    if not map_path.exists():
        raise FileNotFoundError(f"score↔template 映射不存在: {map_path}")
    data = json.loads(map_path.read_text(encoding="utf-8"))
    entries = data.get("entries", data)
    out: dict[str, str] = {}
    for score_id, value in entries.items():
        if isinstance(value, str):
            out[str(score_id)] = value
        elif isinstance(value, dict) and "template_id" in value:
            out[str(score_id)] = str(value["template_id"])
        else:
            raise ValueError(f"非法映射项: {score_id}={value!r}")
    return out


def resolve_template_id(
    score_id: str,
    *,
    template_id: str | None = None,
    map_path: str | Path | None = None,
) -> str:
    """Prefer explicit ``template_id``; otherwise look up ``score_id`` in the map."""
    if template_id:
        return template_id
    mapping = load_score_template_map(map_path)
    if score_id not in mapping:
        raise KeyError(
            f"score_id={score_id!r} 未配置 template_id，"
            f"请传入 template_id 或写入 {map_path or default_score_template_map_path()}"
        )
    return mapping[score_id]
