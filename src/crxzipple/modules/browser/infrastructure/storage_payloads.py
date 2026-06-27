from __future__ import annotations

from typing import Any, Mapping

from crxzipple.modules.browser.domain import BrowserValidationError


def payload_text_any(payload: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def payload_value_any(payload: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload.get(key)
    return None


def payload_bool_any(payload: Mapping[str, Any], *keys: str) -> bool | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            return value
    return None


def payload_number_any(payload: Mapping[str, Any], *keys: str) -> float | None:
    value = payload_value_any(payload, *keys)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BrowserValidationError(f"payload.{keys[0]} must be a number.")
    return float(value)


def payload_int_any(
    payload: Mapping[str, Any],
    *keys: str,
    minimum: int = 0,
) -> int | None:
    value = payload_value_any(payload, *keys)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BrowserValidationError(f"payload.{keys[0]} must be an integer.")
    resolved = int(value)
    if resolved < minimum:
        raise BrowserValidationError(
            f"payload.{keys[0]} must be greater than or equal to {minimum}.",
        )
    return resolved


def payload_limit(payload: Mapping[str, Any], *, default: int, maximum: int = 200) -> int:
    limit = payload_int_any(payload, "limit", "page_size", "pageSize", minimum=1)
    if limit is None:
        limit = default
    return min(limit, maximum)


def payload_skip(payload: Mapping[str, Any]) -> int:
    return payload_int_any(payload, "skip", "skip_count", "skipCount", minimum=0) or 0


__all__ = [
    "payload_bool_any",
    "payload_int_any",
    "payload_limit",
    "payload_number_any",
    "payload_skip",
    "payload_text_any",
    "payload_value_any",
]
