from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def optional_positive_int(value: object, *, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a positive integer.") from exc
    if parsed < 1:
        raise ValueError(f"{label} must be a positive integer.")
    return parsed


def optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip().lower()
        if not stripped:
            return None
        return stripped in {"1", "true", "yes", "on"}
    return bool(value)


def optional_env_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def load_structured_config(path: Path) -> Any:
    raw = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json":
        return json.loads(raw)
    if suffix in {".yaml", ".yml"}:
        return yaml.safe_load(raw)
    raise ValueError(
        f"Unsupported structured config extension '{path.suffix}' for '{path}'.",
    )


def coerce_object_payload(
    raw: object,
    *,
    source_description: str,
) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"{source_description} must decode to an object.")
    return dict(raw)


def deep_merge_dicts(
    base: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = deep_merge_dicts(existing, value)
            continue
        merged[key] = value
    return merged
