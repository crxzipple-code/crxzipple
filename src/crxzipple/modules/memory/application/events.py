from __future__ import annotations

from collections.abc import Callable
from typing import Any

from crxzipple.modules.memory.application.models import MemoryUseContext
from crxzipple.shared.domain.events import Event

MEMORY_CONTEXT_RESOLVED_EVENT = "memory.context.resolved"
MEMORY_CONTEXT_RESOLVE_FAILED_EVENT = "memory.context.resolve_failed"
MEMORY_INDEX_MARKED_DIRTY_EVENT = "memory.index.marked_dirty"
MEMORY_INDEX_SYNC_STARTED_EVENT = "memory.index.sync_started"
MEMORY_INDEX_SYNC_SUCCEEDED_EVENT = "memory.index.sync_succeeded"
MEMORY_INDEX_SYNC_FAILED_EVENT = "memory.index.sync_failed"
MEMORY_RETRIEVAL_STARTED_EVENT = "memory.retrieval.started"
MEMORY_RETRIEVAL_SUCCEEDED_EVENT = "memory.retrieval.succeeded"
MEMORY_RETRIEVAL_FAILED_EVENT = "memory.retrieval.failed"
MEMORY_WRITE_SUCCEEDED_EVENT = "memory.write.succeeded"
MEMORY_WRITE_FAILED_EVENT = "memory.write.failed"

MEMORY_OPERATION_EVENT_NAMES: tuple[str, ...] = (
    MEMORY_CONTEXT_RESOLVED_EVENT,
    MEMORY_CONTEXT_RESOLVE_FAILED_EVENT,
    MEMORY_INDEX_MARKED_DIRTY_EVENT,
    MEMORY_INDEX_SYNC_STARTED_EVENT,
    MEMORY_INDEX_SYNC_SUCCEEDED_EVENT,
    MEMORY_INDEX_SYNC_FAILED_EVENT,
    MEMORY_RETRIEVAL_STARTED_EVENT,
    MEMORY_RETRIEVAL_SUCCEEDED_EVENT,
    MEMORY_RETRIEVAL_FAILED_EVENT,
    MEMORY_WRITE_SUCCEEDED_EVENT,
    MEMORY_WRITE_FAILED_EVENT,
)

MemoryEventEmitter = Callable[[str, dict[str, Any]], None]


def emit_memory_event(
    emitter: MemoryEventEmitter | None,
    event_name: str,
    *,
    context: MemoryUseContext | None = None,
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
        **_context_payload(context),
        **(payload or {}),
    }
    try:
        emitter(event_name, body)
    except Exception:
        return


def memory_event_from_payload(event_name: str, payload: dict[str, Any]) -> Event:
    space_id = _text(payload.get("space_id"))
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
        ordering_key=space_id or _text(payload.get("owner_id")),
        trace=trace,
    )


def _context_payload(context: MemoryUseContext | None) -> dict[str, Any]:
    if context is None:
        return {}
    return {
        "space_id": context.space_id,
        "storage_root": context.storage_root,
        "retrieval_backend": context.retrieval_backend,
        "owner_id": context.space_id,
        "owner_kind": "memory_space",
    }


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
