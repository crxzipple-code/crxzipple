from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
)
from crxzipple.modules.operations.application.read_models.orchestration_event_log_projection import (
    display,
    event_details,
    event_display_label,
    event_entity_id,
    event_level_from_name,
    event_name,
    event_payload,
    event_source,
    event_status_from_name,
    event_summary,
    event_tone_from_name,
    event_trace_id,
    optional_str,
    trace_route_from_id,
)
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc


def event_record_time(record: Any) -> datetime:
    occurred_at = getattr(record, "occurred_at", None)
    if isinstance(occurred_at, datetime):
        return coerce_utc_datetime(occurred_at)
    event = getattr(record, "envelope", None)
    occurred_at = getattr(event, "occurred_at", None)
    if isinstance(occurred_at, datetime):
        return coerce_utc_datetime(occurred_at)
    return datetime.min


def event_record_row(record: Any) -> OperationsTableRowModel:
    if isinstance(record, OperationsObservedEvent):
        return _observed_event_row(record)
    event = getattr(record, "envelope", None)
    payload = event_payload(event)
    name = event_name(event, payload)
    run_id = optional_str(payload.get("run_id"))
    entity_id = event_entity_id(payload, fallback=run_id or name)
    trace_id = event_trace_id(event, payload, fallback=run_id)
    return OperationsTableRowModel(
        id=display(getattr(record, "cursor", None) or getattr(event, "id", None)),
        cells={
            "time": format_datetime_utc(event_record_time(record)),
            "level": event_level_from_name(name, payload),
            "event": event_display_label(name, payload),
            "event_key": name,
            "run_id": display(run_id),
            "run_id_entity": display(entity_id),
            "source": event_source(name, payload),
            "summary": event_summary(name, payload),
            "details": event_details(payload),
            "route": f"/ui/workbench/runs/{run_id}" if run_id else "-",
            "trace_route": trace_route_from_id(trace_id),
        },
        status=event_status_from_name(name, payload),
        tone=event_tone_from_name(name, payload),
    )


def _observed_event_row(event: OperationsObservedEvent) -> OperationsTableRowModel:
    payload = dict(event.payload)
    run_id = event.run_id or optional_str(payload.get("run_id"))
    trace_id = event.trace_id or event_trace_id(event, payload, fallback=run_id)
    return OperationsTableRowModel(
        id=display(event.cursor or event.id),
        cells={
            "time": format_datetime_utc(event.occurred_at),
            "level": event.level,
            "event": event_display_label(event.event_name, payload),
            "event_key": event.event_name,
            "run_id": display(run_id),
            "run_id_entity": display(event.entity_id),
            "source": event_source(event.event_name, payload),
            "summary": event_summary(event.event_name, payload),
            "details": event_details(payload),
            "route": f"/ui/workbench/runs/{run_id}" if run_id else "-",
            "trace_route": trace_route_from_id(trace_id),
        },
        status=event.status,
        tone="danger"
        if event.level == "error"
        else "warning"
        if event.level == "warning"
        else "info",
    )
