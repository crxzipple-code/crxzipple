from __future__ import annotations

from collections.abc import Callable
from typing import Any

from crxzipple.shared.domain.events import Event

BROWSER_PROFILE_CREATED_EVENT = "browser.profile.created"
BROWSER_PROFILE_UPDATED_EVENT = "browser.profile.updated"
BROWSER_PROFILE_DELETED_EVENT = "browser.profile.deleted"
BROWSER_PROFILE_ENABLED_EVENT = "browser.profile.enabled"
BROWSER_PROFILE_DISABLED_EVENT = "browser.profile.disabled"
BROWSER_POOL_CREATED_EVENT = "browser.pool.created"
BROWSER_POOL_UPDATED_EVENT = "browser.pool.updated"
BROWSER_POOL_DELETED_EVENT = "browser.pool.deleted"
BROWSER_POOL_ENABLED_EVENT = "browser.pool.enabled"
BROWSER_POOL_DISABLED_EVENT = "browser.pool.disabled"
BROWSER_ALLOCATION_ACQUIRED_EVENT = "browser.allocation.acquired"
BROWSER_ALLOCATION_HEARTBEATED_EVENT = "browser.allocation.heartbeated"
BROWSER_ALLOCATION_RELEASED_EVENT = "browser.allocation.released"
BROWSER_ALLOCATION_EXPIRED_EVENT = "browser.allocation.expired"
BROWSER_ALLOCATION_FAILED_EVENT = "browser.allocation.failed"
BROWSER_ALLOCATION_LOST_EVENT = "browser.allocation.lost"
BROWSER_NETWORK_CAPTURE_STARTED_EVENT = "browser.network.capture.started"
BROWSER_NETWORK_CAPTURE_STOPPED_EVENT = "browser.network.capture.stopped"
BROWSER_NETWORK_REQUEST_OBSERVED_EVENT = "browser.network.request.observed"
BROWSER_NETWORK_REQUEST_FAILED_EVENT = "browser.network.request.failed"
BROWSER_NETWORK_FETCH_EXECUTED_EVENT = "browser.network.fetch.executed"
BROWSER_NETWORK_FETCH_FAILED_EVENT = "browser.network.fetch.failed"
BROWSER_NETWORK_REPLAY_EXECUTED_EVENT = "browser.network.replay.executed"
BROWSER_NETWORK_REPLAY_FAILED_EVENT = "browser.network.replay.failed"
BROWSER_ENVIRONMENT_CHANGED_EVENT = "browser.environment.changed"
BROWSER_DIAGNOSTICS_COLLECTED_EVENT = "browser.diagnostics.collected"
BROWSER_TRACE_STARTED_EVENT = "browser.trace.started"
BROWSER_TRACE_EXPORTED_EVENT = "browser.trace.exported"

BROWSER_OPERATION_EVENT_NAMES: tuple[str, ...] = (
    BROWSER_PROFILE_CREATED_EVENT,
    BROWSER_PROFILE_UPDATED_EVENT,
    BROWSER_PROFILE_DELETED_EVENT,
    BROWSER_PROFILE_ENABLED_EVENT,
    BROWSER_PROFILE_DISABLED_EVENT,
    BROWSER_POOL_CREATED_EVENT,
    BROWSER_POOL_UPDATED_EVENT,
    BROWSER_POOL_DELETED_EVENT,
    BROWSER_POOL_ENABLED_EVENT,
    BROWSER_POOL_DISABLED_EVENT,
    BROWSER_ALLOCATION_ACQUIRED_EVENT,
    BROWSER_ALLOCATION_HEARTBEATED_EVENT,
    BROWSER_ALLOCATION_RELEASED_EVENT,
    BROWSER_ALLOCATION_EXPIRED_EVENT,
    BROWSER_ALLOCATION_FAILED_EVENT,
    BROWSER_ALLOCATION_LOST_EVENT,
    BROWSER_NETWORK_CAPTURE_STARTED_EVENT,
    BROWSER_NETWORK_CAPTURE_STOPPED_EVENT,
    BROWSER_NETWORK_REQUEST_OBSERVED_EVENT,
    BROWSER_NETWORK_REQUEST_FAILED_EVENT,
    BROWSER_NETWORK_FETCH_EXECUTED_EVENT,
    BROWSER_NETWORK_FETCH_FAILED_EVENT,
    BROWSER_NETWORK_REPLAY_EXECUTED_EVENT,
    BROWSER_NETWORK_REPLAY_FAILED_EVENT,
    BROWSER_ENVIRONMENT_CHANGED_EVENT,
    BROWSER_DIAGNOSTICS_COLLECTED_EVENT,
    BROWSER_TRACE_STARTED_EVENT,
    BROWSER_TRACE_EXPORTED_EVENT,
)

BrowserEventEmitter = Callable[[str, dict[str, Any]], None]


def emit_browser_event(
    emitter: BrowserEventEmitter | None,
    event_name: str,
    *,
    payload: dict[str, Any] | None = None,
    status: str = "observed",
    level: str = "info",
) -> None:
    if emitter is None:
        return
    body = {
        "event_name": event_name,
        "status": status,
        "level": level,
        **(payload or {}),
    }
    try:
        emitter(event_name, body)
    except Exception:
        return


def browser_event_from_payload(event_name: str, payload: dict[str, Any]) -> Event:
    trace: dict[str, Any] = {}
    for key in ("trace_id", "correlation_id", "source_event_id"):
        value = _text(payload.get(key))
        if value:
            trace[key] = value
    return Event(
        name=event_name,
        kind="observe",
        payload={
            "event_name": event_name,
            **payload,
        },
        ordering_key=_text(payload.get("profile_name")) or _text(payload.get("pool_id")),
        trace=trace,
    )


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


__all__ = [
    "BROWSER_ALLOCATION_ACQUIRED_EVENT",
    "BROWSER_ALLOCATION_EXPIRED_EVENT",
    "BROWSER_ALLOCATION_FAILED_EVENT",
    "BROWSER_ALLOCATION_HEARTBEATED_EVENT",
    "BROWSER_ALLOCATION_LOST_EVENT",
    "BROWSER_ALLOCATION_RELEASED_EVENT",
    "BROWSER_ENVIRONMENT_CHANGED_EVENT",
    "BROWSER_DIAGNOSTICS_COLLECTED_EVENT",
    "BROWSER_NETWORK_CAPTURE_STARTED_EVENT",
    "BROWSER_NETWORK_CAPTURE_STOPPED_EVENT",
    "BROWSER_NETWORK_FETCH_EXECUTED_EVENT",
    "BROWSER_NETWORK_FETCH_FAILED_EVENT",
    "BROWSER_NETWORK_REQUEST_FAILED_EVENT",
    "BROWSER_NETWORK_REQUEST_OBSERVED_EVENT",
    "BROWSER_NETWORK_REPLAY_EXECUTED_EVENT",
    "BROWSER_NETWORK_REPLAY_FAILED_EVENT",
    "BROWSER_OPERATION_EVENT_NAMES",
    "BROWSER_TRACE_EXPORTED_EVENT",
    "BROWSER_TRACE_STARTED_EVENT",
    "BROWSER_POOL_CREATED_EVENT",
    "BROWSER_POOL_DELETED_EVENT",
    "BROWSER_POOL_DISABLED_EVENT",
    "BROWSER_POOL_ENABLED_EVENT",
    "BROWSER_POOL_UPDATED_EVENT",
    "BROWSER_PROFILE_CREATED_EVENT",
    "BROWSER_PROFILE_DELETED_EVENT",
    "BROWSER_PROFILE_DISABLED_EVENT",
    "BROWSER_PROFILE_ENABLED_EVENT",
    "BROWSER_PROFILE_UPDATED_EVENT",
    "BrowserEventEmitter",
    "browser_event_from_payload",
    "emit_browser_event",
]
