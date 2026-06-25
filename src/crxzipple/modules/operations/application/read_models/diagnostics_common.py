from __future__ import annotations

from typing import Any


def enum_value(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip()


def optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def optional_int(value: object, *, fallback: int = 0) -> int:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return fallback


def as_list(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def summary_payload(item: Any) -> dict[str, object]:
    payload = getattr(item, "summary_payload", None)
    return dict(payload) if isinstance(payload, dict) else {}


def summary_list(payload: dict[str, object], key: str) -> tuple[object, ...]:
    value = payload.get(key)
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return ()


def contains_key(value: object, keys: set[str]) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key) in keys:
                return True
            if contains_key(child, keys):
                return True
    if isinstance(value, (list, tuple)):
        return any(contains_key(item, keys) for item in value)
    return False


def has_any_key(value: object, keys: set[str]) -> bool:
    return contains_key(value, keys)


def has_key(value: object, key: str) -> bool:
    return isinstance(value, dict) and key in value


def joined_text_values(value: object) -> str:
    if isinstance(value, dict):
        return "\n".join(joined_text_values(child) for child in value.values())
    if isinstance(value, (list, tuple)):
        return "\n".join(joined_text_values(child) for child in value)
    text = optional_text(value)
    return text or ""
