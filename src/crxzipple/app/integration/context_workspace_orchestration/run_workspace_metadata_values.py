"""Shared value formatting helpers for run workspace metadata."""

from __future__ import annotations

import json

from ._metadata import metadata_text


def metadata_list(value: object) -> list[object]:
    return list(value) if isinstance(value, (list, tuple)) else []


def metadata_string_list(value: object) -> list[str]:
    if isinstance(value, str):
        candidates: tuple[object, ...] = (value,)
    elif isinstance(value, (list, tuple, set, frozenset)):
        candidates = tuple(value)
    else:
        return []
    items: list[str] = []
    for item in candidates:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if normalized and normalized not in items:
            items.append(normalized)
    return items


def payload_text(value: object, *, limit: int = 4000) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()[:limit].rstrip()
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)[:limit].rstrip()
    except TypeError:
        return str(value).strip()[:limit].rstrip()


def dict_payload(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def display_number(value: object) -> str:
    if isinstance(value, int | float):
        return str(value)
    return "-"


def yes_no(value: bool) -> str:
    return "yes" if value else "no"


def metadata_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = metadata_text(value)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def public_payload_summary(
    payload: dict[str, object],
    *,
    keys: tuple[str, ...],
) -> str:
    parts: list[str] = []
    for key in keys:
        value = metadata_text(payload.get(key))
        if value is not None:
            parts.append(f"{key}={value}")
    return ", ".join(parts) if parts else "present"
