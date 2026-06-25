from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.shared.time import coerce_utc_datetime

WARMUP_EVENT_NAMES = {
    "llm.profile_warmup_succeeded",
    "llm.profile_warmup_skipped",
    "llm.profile_warmup_failed",
}


def latest_warmup_events_by_profile(
    events: tuple[OperationsObservedEvent, ...],
) -> dict[str, OperationsObservedEvent]:
    result: dict[str, OperationsObservedEvent] = {}
    for event in sorted(
        events,
        key=lambda item: coerce_utc_datetime(item.occurred_at),
        reverse=True,
    ):
        if event.event_name not in WARMUP_EVENT_NAMES:
            continue
        payload = event.payload if isinstance(event.payload, dict) else {}
        profile_id = _text(payload.get("llm_id")) or event.entity_id
        if not profile_id or profile_id in result:
            continue
        result[profile_id] = event
    return result


def warmup_status_label(event: OperationsObservedEvent | None) -> str:
    if event is None:
        return "Not checked"
    payload = event.payload if isinstance(event.payload, dict) else {}
    status = _text(payload.get("status")) or event.status
    transport = _text(payload.get("transport"))
    if event.event_name == "llm.profile_warmup_succeeded":
        return f"Warmed ({transport})" if transport else "Warmed"
    if event.event_name == "llm.profile_warmup_skipped":
        reason = _text(payload.get("reason"))
        return f"Skipped: {reason}" if reason else "Skipped"
    if event.event_name == "llm.profile_warmup_failed":
        reason = _text(payload.get("reason"))
        return f"Failed: {reason}" if reason else "Failed"
    return status or "-"


def warmup_tone(
    event: OperationsObservedEvent | None,
    *,
    fallback: str,
) -> str:
    if event is None:
        return fallback
    if event.event_name == "llm.profile_warmup_succeeded":
        return "success"
    if event.event_name == "llm.profile_warmup_skipped":
        return "warning"
    if event.event_name == "llm.profile_warmup_failed":
        return "danger"
    return fallback


def warmup_next_action(
    event: OperationsObservedEvent | None,
    *,
    readiness: dict[str, Any],
) -> str:
    if not readiness.get("ready"):
        return "Open Access"
    if event is None:
        return "Run warmup"
    if event.event_name == "llm.profile_warmup_succeeded":
        return "Ready for run"
    if event.event_name == "llm.profile_warmup_skipped":
        return "Use invoke smoke"
    if event.event_name == "llm.profile_warmup_failed":
        reason = warmup_reason(event).lower()
        if "credential" in reason or "oauth" in reason or "token" in reason:
            return "Check Access then retry warmup"
        if "websocket" in reason or "connection" in reason or "endpoint" in reason:
            return "Check WebSocket transport"
        return "Retry warmup / inspect event"
    return "-"


def warmup_reason(event: OperationsObservedEvent) -> str:
    payload = event.payload if isinstance(event.payload, dict) else {}
    reason = _text(payload.get("reason"))
    if reason:
        return reason
    details = payload.get("details")
    if isinstance(details, dict):
        return _text(details.get("reason")) or ""
    return ""


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
