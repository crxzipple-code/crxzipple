from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.events_event_common import (
    columns,
    contract_status_label,
    display,
    event_tone,
)
from crxzipple.modules.operations.application.read_models.events_filters import (
    recent_empty_state,
)
from crxzipple.modules.operations.application.read_models.events_models import (
    EventsOperationsQuery,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.routes import (
    workbench_trace_route,
)


def recent_events_table(
    events: list[dict[str, Any]],
    *,
    total: int,
    query: EventsOperationsQuery,
) -> OperationsTableSectionModel:
    rows = tuple(_recent_event_row(item) for item in events)
    return OperationsTableSectionModel(
        id="recent_events",
        title="Recent Events",
        columns=columns(
            ("time", "Time"),
            ("owner", "Owner"),
            ("event", "Event"),
            ("kind", "Kind"),
            ("topic", "Topic"),
            ("cursor", "Cursor"),
            ("status", "Status"),
            ("contract", "Contract"),
            ("trace", "Trace"),
            ("run", "Run ID / Entity"),
        ),
        rows=rows,
        total=total,
        view_all_route="/operations/events?tab=recent",
        empty_state=recent_empty_state(query),
    )


def _recent_event_row(item: dict[str, Any]) -> OperationsTableRowModel:
    return OperationsTableRowModel(
        id=_event_row_id(item),
        cells={
            "time": display(item.get("created_at")),
            "owner": display(item.get("owner")),
            "event": display(item.get("event_name")),
            "kind": display(item.get("kind")),
            "topic": display(item.get("topic")),
            "cursor": display(item.get("cursor")),
            "event_id": display(item.get("event_id")),
            "status": contract_status_label(display(item.get("contract_status"))),
            "contract": display(item.get("contract_label")),
            "trace": display(item.get("trace_id")),
            "run": display(item.get("run_id") or item.get("entity_id")),
            "route": _trace_route(item),
            "trace_route": _trace_route(item),
        },
        status=display(item.get("contract_status")),
        tone=event_tone(item),
    )


def _trace_route(item: dict[str, Any]) -> str:
    trace_id = display(item.get("trace_id"))
    return workbench_trace_route(None if trace_id == "-" else trace_id)


def _event_row_id(item: dict[str, Any]) -> str:
    event_id = display(item.get("event_id"))
    if event_id != "-":
        return event_id
    return f"{display(item.get('topic'))}:{display(item.get('cursor'))}"
