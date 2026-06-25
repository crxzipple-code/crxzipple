from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.access_common import (
    status_label,
    tone_for_status,
)
from crxzipple.modules.operations.application.read_models.access_target_projection import (
    impact,
    target_label,
    target_reason,
    target_worst_status,
)
from crxzipple.modules.operations.application.read_models.access_values import (
    text,
)
from crxzipple.modules.operations.application.read_models.access_events import (
    event_details,
    event_tone,
    short_event_name,
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


def access_audit_summary_table(
    events: tuple[OperationsObservedEvent, ...],
) -> OperationsTableSectionModel:
    rows = [
        OperationsTableRowModel(
            id=f"{event.topic}:{event.cursor or event.id}",
            cells={
                "time": format_datetime_utc(event.occurred_at),
                "action": event.event_name,
                "target": event.entity_id or "-",
                "status": event.status or event.level,
                "operator": text(event.payload.get("operator") or event.payload.get("actor")),
                "source": event.topic,
                "reason": text(
                    event.payload.get("reason")
                    or event.payload.get("error")
                    or event.payload.get("status"),
                ),
            },
            status=event.status,
            tone=tone_for_status(event.status or event.level),
        )
        for event in events
    ]
    return OperationsTableSectionModel(
        id="access_audit_summary",
        title="Audit Summary",
        columns=(
            OperationsTableColumnModel("time", "Time"),
            OperationsTableColumnModel("action", "Action"),
            OperationsTableColumnModel("target", "Target"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("operator", "Operator"),
            OperationsTableColumnModel("source", "Source"),
            OperationsTableColumnModel("reason", "Reason"),
        ),
        rows=tuple(rows[:120]),
        total=len(rows),
        empty_state="No access audit records.",
    )


def access_events_table(
    events: tuple[OperationsObservedEvent, ...],
) -> OperationsTableSectionModel:
    rows = [
        OperationsTableRowModel(
            id=text(event.cursor or event.id, ""),
            cells={
                "time": format_datetime_utc(coerce_utc_datetime(event.occurred_at)),
                "level": event.level,
                "event": short_event_name(event.event_name),
                "entity": text(event.entity_id),
                "status": status_label(event.status),
                "details": event_details(event.payload),
                "trace": text(event.trace_id),
                "trace_route": workbench_trace_route(event.trace_id),
            },
            status=event.status,
            tone=event_tone(event),
        )
        for event in events[:100]
    ]
    return OperationsTableSectionModel(
        id="recent_access_events",
        title="Recent Access Events",
        columns=(
            OperationsTableColumnModel("time", "Time"),
            OperationsTableColumnModel("level", "Level"),
            OperationsTableColumnModel("event", "Event"),
            OperationsTableColumnModel("entity", "Entity"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("details", "Details"),
            OperationsTableColumnModel("trace", "Trace"),
        ),
        rows=tuple(rows),
        total=len(events),
        empty_state="No access events.",
    )


def fallback_problems_table(
    *,
    targets: tuple[dict[str, Any], ...],
    events: tuple[OperationsObservedEvent, ...],
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for target in targets:
        rows.append(
            OperationsTableRowModel(
                id=f"target:{text(target.get('resource_id'), '')}",
                cells={
                    "entity": target_label(target),
                    "reason": target_reason(target),
                    "status": status_label(target_worst_status(target)),
                    "impact": impact(target),
                    "trace": "-",
                },
                status=target_worst_status(target),
                tone=tone_for_status(target_worst_status(target)),
            )
        )
    for event in events:
        if event.level != "error" and event.status not in {"failed", "error"}:
            continue
        rows.append(
            OperationsTableRowModel(
                id=f"event:{event.cursor or event.id}",
                cells={
                    "entity": text(event.entity_id),
                    "reason": event_details(event.payload),
                    "status": status_label(event.status),
                    "impact": "High" if event.level == "error" else "Medium",
                    "trace": text(event.trace_id),
                    "trace_route": workbench_trace_route(event.trace_id),
                },
                status=event.status,
                tone=event_tone(event),
            )
        )
    return OperationsTableSectionModel(
        id="fallback_problems",
        title="Fallback / Resolver Problems",
        columns=(
            OperationsTableColumnModel("entity", "Entity"),
            OperationsTableColumnModel("reason", "Reason"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("impact", "Impact"),
            OperationsTableColumnModel("trace", "Trace"),
        ),
        rows=tuple(rows[:120]),
        total=len(rows),
        empty_state="No fallback or resolver problems.",
    )
