from __future__ import annotations

from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.presenters import (
    title_label,
)
from crxzipple.modules.operations.application.read_models.routes import (
    workbench_trace_route,
)
from crxzipple.modules.operations.application.read_models.tool_lifecycle_event_projection import (
    columns,
    display,
    optional_str,
    short_tool_event_name,
    source_label,
    source_route,
    tool_event_details,
    tool_event_tone,
    tool_event_trace_id,
    tool_label,
    tool_label_from_id,
)
from crxzipple.modules.tool.domain import Tool, ToolRun
from crxzipple.shared.time import format_datetime_utc


def tool_worker_events_section(
    events: list[OperationsObservedEvent],
) -> OperationsTableSectionModel:
    rows = tuple(
        tool_lifecycle_event_row(
            event,
            tools_by_id={},
            runs_by_id={},
        )
        for event in sorted(events, key=lambda item: item.occurred_at, reverse=True)[:20]
    )
    return OperationsTableSectionModel(
        id="worker_events",
        title="Worker Events",
        columns=columns(
            ("time", "Time"),
            ("level", "Level"),
            ("event", "Event"),
            ("status", "Status"),
            ("details", "Details"),
            ("trace", "Trace"),
        ),
        rows=rows,
        total=len(events),
        empty_state="No observed events retained for this worker.",
    )


def tool_run_events_section(
    events: list[OperationsObservedEvent],
    *,
    tools_by_id: dict[str, Tool],
    run: ToolRun,
) -> OperationsTableSectionModel:
    rows = tuple(
        tool_lifecycle_event_row(
            event,
            tools_by_id=tools_by_id,
            runs_by_id={run.id: run},
        )
        for event in sorted(events, key=lambda item: item.occurred_at, reverse=True)[:20]
    )
    return OperationsTableSectionModel(
        id="run_events",
        title="Run Events",
        columns=columns(
            ("time", "Time"),
            ("level", "Level"),
            ("event", "Event"),
            ("status", "Status"),
            ("worker", "Worker ID"),
            ("assignment", "Assignment"),
            ("details", "Details"),
            ("trace", "Trace"),
        ),
        rows=rows,
        total=len(events),
        empty_state="No observed events retained for this run.",
    )


def tool_lifecycle_event_row(
    event: OperationsObservedEvent,
    *,
    tools_by_id: dict[str, Tool],
    runs_by_id: dict[str, ToolRun],
) -> OperationsTableRowModel:
    payload = dict(event.payload)
    run_id = event.run_id or optional_str(payload.get("run_id"))
    run = runs_by_id.get(run_id or "")
    tool_id = optional_str(payload.get("tool_id")) or (
        run.tool_id if run is not None else None
    )
    assignment_id = optional_str(payload.get("assignment_id"))
    worker_id = optional_str(payload.get("worker_id")) or (
        run.worker_id if run is not None else None
    )
    trace_id = tool_event_trace_id(event, run)
    route = source_route(run) if run is not None else "-"
    return OperationsTableRowModel(
        id=display(event.cursor or event.id),
        cells={
            "time": format_datetime_utc(event.occurred_at),
            "level": title_label(event.level),
            "event": short_tool_event_name(event.event_name),
            "tool": (
                tool_label(run, tools_by_id)
                if run is not None
                else tool_label_from_id(tool_id, tools_by_id)
            ),
            "run_id": display(run_id),
            "assignment": display(assignment_id),
            "worker": display(worker_id),
            "status": display(event.status),
            "source": source_label(run) if run is not None else "Event Bus",
            "details": tool_event_details(payload),
            "trace": display(trace_id),
            "route": route,
            "trace_route": workbench_trace_route(trace_id),
        },
        status=event.status,
        tone=tool_event_tone(event),
    )
