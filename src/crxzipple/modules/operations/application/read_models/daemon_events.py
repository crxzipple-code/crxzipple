from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.daemon_common import (
    _first_text,
    _short,
    _status_label,
    _text,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.routes import (
    workbench_trace_route,
)
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc


def daemon_events_table(
    events: tuple[OperationsObservedEvent, ...],
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for event in events[:80]:
        payload = dict(event.payload)
        service_key = _first_text(
            payload.get("service_key"),
            payload.get("daemon_service_key"),
            event.entity_id,
        )
        rows.append(
            OperationsTableRowModel(
                id=_text(event.cursor or event.id, ""),
                cells={
                    "time": format_datetime_utc(coerce_utc_datetime(event.occurred_at)),
                    "level": event.level,
                    "event": _short_event_name(event.event_name),
                    "service_key": service_key,
                    "entity": _text(event.entity_id),
                    "status": _status_label(event.status),
                    "details": _event_details(payload),
                    "trace": _text(event.trace_id),
                    "trace_route": workbench_trace_route(event.trace_id),
                },
                status=event.status,
                tone=_event_tone(event),
            )
        )
    return OperationsTableSectionModel(
        id="daemon_events",
        title="Daemon Events",
        columns=(
            OperationsTableColumnModel("time", "Time"),
            OperationsTableColumnModel("level", "Level"),
            OperationsTableColumnModel("event", "Event"),
            OperationsTableColumnModel("service_key", "Service Key"),
            OperationsTableColumnModel("entity", "Entity"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("details", "Details"),
            OperationsTableColumnModel("trace", "Trace"),
        ),
        rows=tuple(rows),
        total=len(events),
        empty_state="No records.",
    )


def _event_tone(event: OperationsObservedEvent) -> str:
    if event.level == "error" or event.status in {"failed", "error"}:
        return "danger"
    if event.level == "warning" or event.status in {"warning", "degraded"}:
        return "warning"
    return "success" if event.status in {"completed", "success", "observed"} else "neutral"


def _event_details(payload: dict[str, Any]) -> str:
    for key in (
        "summary",
        "message",
        "reason",
        "error_message",
        "status",
        "component",
        "service_key",
    ):
        value = payload.get(key)
        if value is not None and _text(value, "") != "-":
            return _short(value, 120)
    return "-"


def _short_event_name(event_name: str) -> str:
    value = event_name
    for prefix in ("daemon.", "crxzipple."):
        if value.startswith(prefix):
            return value[len(prefix) :]
    return value
