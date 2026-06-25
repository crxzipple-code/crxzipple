from __future__ import annotations

from datetime import datetime

from crxzipple.modules.events.application.read_models import (
    TraceEventView,
    TraceSummaryView,
)
from crxzipple.modules.events.application.read_models.trace import TraceLinkedEntity


def trace_summary_from_events(
    trace_id: str,
    events: tuple[TraceEventView, ...],
) -> TraceSummaryView:
    timestamps = [
        datetime.fromisoformat(event.timestamp)
        for event in events
        if event.timestamp
    ]
    started_at = min(timestamps) if timestamps else None
    completed_at = max(timestamps) if timestamps else None
    linked_entities = _unique_trace_entities(
        entity for event in events for entity in event.linked_entities
    )
    return TraceSummaryView(
        trace_id=trace_id,
        status=_trace_status(events),
        started_at=started_at.isoformat() if started_at is not None else None,
        completed_at=completed_at.isoformat() if completed_at is not None else None,
        duration_ms=_trace_span_ms(started_at, completed_at),
        event_count=len(events),
        key_event_count=sum(1 for event in events if event.key_event),
        owners=tuple(sorted({event.owner for event in events if event.owner})),
        linked_entities=linked_entities,
    )


def _unique_trace_entities(items) -> tuple[TraceLinkedEntity, ...]:  # noqa: ANN001
    seen: set[tuple[str, str]] = set()
    unique: list[TraceLinkedEntity] = []
    for item in items:
        key = (item.type, item.id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return tuple(unique)


def _trace_status(events: tuple[TraceEventView, ...]) -> str:
    if any(event.status == "failed" for event in events):
        return "failed"
    if any(event.status in {"running", "queued", "waiting"} for event in events):
        return "running"
    if events:
        return "success"
    return "unknown"


def _trace_span_ms(
    started_at: datetime | None,
    completed_at: datetime | None,
) -> int | None:
    if started_at is None or completed_at is None:
        return None
    return max(int((completed_at - started_at).total_seconds() * 1000), 0)
