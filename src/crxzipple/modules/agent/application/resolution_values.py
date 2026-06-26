from __future__ import annotations

from typing import Any


def dict_payload(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def text_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if not isinstance(value, (list, tuple, set)):
        return ()
    return tuple(
        str(item).strip()
        for item in value
        if item is not None and str(item).strip()
    )


def enum_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple, set)):
        return ()
    return tuple(enum_value(item) for item in value if enum_value(item) is not None)


def enum_value(value: object) -> str | None:
    raw = getattr(value, "value", value)
    return optional_text(raw)


def optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "dict_payload",
    "enum_tuple",
    "enum_value",
    "optional_int",
    "optional_text",
    "text_tuple",
]
