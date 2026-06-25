from __future__ import annotations

import json
from typing import Any


def safe_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def short_json(value: Any, *, size: int = 80) -> str:
    text_value = safe_json(value)
    if text_value in {"{}", "[]", "null"}:
        return "-"
    if len(text_value) <= size:
        return text_value
    return f"{text_value[: max(12, size - 8)]}..."


def display_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): display_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [display_payload(item) for item in value]
    if isinstance(value, tuple):
        return tuple(display_payload(item) for item in value)
    if isinstance(value, str):
        return value
    return value
