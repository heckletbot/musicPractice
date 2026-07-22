"""Serialize module results for tests and debugging."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any

from music_practice.types import ObservationDict


def to_observable_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "to_dict") and callable(value.to_dict):
        data = value.to_dict()
        if isinstance(data, dict):
            return data
    if hasattr(value, "to_summary") and callable(value.to_summary):
        data = value.to_summary()
        if isinstance(data, dict):
            return data
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return {"items": [to_observable_dict(item) for item in value]}
    raise TypeError(f"Cannot observe value of type {type(value)!r}")


def observe(value: Any, *, kind: str | None = None) -> ObservationDict:
    data = to_observable_dict(value)
    resolved_kind = kind or type(value).__name__
    return {"kind": resolved_kind, "data": data}


def format_observation(value: Any, *, kind: str | None = None, indent: int = 2) -> str:
    payload = observe(value, kind=kind)
    return json.dumps(payload, ensure_ascii=False, indent=indent)
