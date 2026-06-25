from __future__ import annotations

from typing import Any


def normalized_filter(value: Any) -> str:
    normalized = text(value, "all").strip().lower().replace(" ", "_").replace("-", "_")
    return normalized or "all"


def list_value(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [text(item, "") for item in value if text(item, "")]
    return []


def text(value: Any, default: str = "-") -> str:
    if value is None:
        return default
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set)):
        return ", ".join(text(item, "") for item in value if text(item, ""))
    if isinstance(value, dict):
        return ", ".join(
            f"{key}={text(item, '')}" for key, item in sorted(value.items())
        )
    result = str(value).strip()
    return result if result else default


def short(value: Any, limit: int = 80) -> str:
    result = text(value)
    if len(result) <= limit:
        return result
    return f"{result[: max(0, limit - 1)]}..."


def int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)
