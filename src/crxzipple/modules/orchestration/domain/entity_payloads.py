"""Payload and normalization helpers for orchestration domain entities."""

from __future__ import annotations

from datetime import datetime

WAITING_REASON_MAX_CHARS = 100

def _optional_payload_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None

def _optional_datetime_payload(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None

def _optional_payload_dict(value: object) -> dict[str, object] | None:
    return dict(value) if isinstance(value, dict) else None

def _active_run_ids_from_metadata(metadata: dict[str, object]) -> list[str]:
    runtime_state = metadata.get("runtime_state")
    if not isinstance(runtime_state, dict):
        return []
    raw_active_run_ids = runtime_state.get("active_run_ids")
    if not isinstance(raw_active_run_ids, (list, tuple, set)):
        return []
    return [
        text
        for item in raw_active_run_ids
        for text in (_optional_payload_text(item),)
        if text is not None
    ]

def _normalized_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None

def _waiting_reason(value: str | None) -> str | None:
    normalized = _normalized_optional_text(value)
    if normalized is None:
        return None
    if len(normalized) <= WAITING_REASON_MAX_CHARS:
        return normalized
    return f"{normalized[: WAITING_REASON_MAX_CHARS - 3]}..."

def _normalized_payload(value: dict[str, object] | None) -> dict[str, object] | None:
    if value is None:
        return None
    return dict(value)
