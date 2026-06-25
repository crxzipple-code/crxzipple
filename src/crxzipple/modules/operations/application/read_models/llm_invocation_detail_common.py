from __future__ import annotations

from typing import Any


def int_value(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    if isinstance(value, str):
        try:
            return max(int(value), 0)
        except ValueError:
            return 0
    return 0


def optional_int_label(value: Any) -> str:
    parsed = int_value(value)
    return str(parsed) if parsed else "-"


def duration_seconds_label(value: Any) -> str:
    parsed = int_value(value)
    if not parsed:
        return "-"
    if parsed % 86_400 == 0:
        return f"{parsed // 86_400}d"
    if parsed % 3_600 == 0:
        return f"{parsed // 3_600}h"
    return f"{parsed}s"


def text_or_dash(value: Any) -> str:
    text = str(value or "").strip()
    return text or "-"


def text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def truncate(value: Any, limit: int = 160) -> str:
    normalized = str(value)
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit]}..."


def bounded_text(value: str, *, limit: int) -> str:
    if len(value) <= limit:
        return value
    if limit <= 1:
        return value[:limit]
    return value[: limit - 1].rstrip() + "…"
