from __future__ import annotations


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def bool_value(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


__all__ = ["bool_value", "normalize_optional_text"]
