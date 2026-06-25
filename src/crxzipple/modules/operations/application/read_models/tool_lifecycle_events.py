from __future__ import annotations

from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.tool_lifecycle_event_projection import (
    columns,
    tool_lifecycle_display_priority,
    tool_lookup,
)
from crxzipple.modules.operations.application.read_models.tool_lifecycle_event_rows import (
    tool_lifecycle_event_row,
)
from crxzipple.modules.tool.domain import Tool, ToolRun
from crxzipple.shared.time import coerce_utc_datetime


def tool_lifecycle_events_section(
    events: tuple[OperationsObservedEvent, ...],
    *,
    tools: list[Tool],
    runs: list[ToolRun],
) -> OperationsTableSectionModel:
    tools_by_id = tool_lookup(tools)
    runs_by_id = {run.id: run for run in runs}
    visible_events = sorted(
        events,
        key=lambda event: (
            tool_lifecycle_display_priority(event.event_name),
            -coerce_utc_datetime(event.occurred_at).timestamp(),
        ),
    )
    rows = tuple(
        tool_lifecycle_event_row(
            event,
            tools_by_id=tools_by_id,
            runs_by_id=runs_by_id,
        )
        for event in visible_events[:80]
    )
    return OperationsTableSectionModel(
        id="tool_lifecycle_events",
        title="Tool Lifecycle Events",
        columns=columns(
            ("time", "Time"),
            ("level", "Level"),
            ("event", "Event"),
            ("tool", "Tool"),
            ("run_id", "Run ID"),
            ("assignment", "Assignment"),
            ("worker", "Worker ID"),
            ("status", "Status"),
            ("source", "Source"),
            ("details", "Details"),
            ("trace", "Trace"),
        ),
        rows=rows,
        total=len(events),
        view_all_route="/operations/tool?tab=events",
        empty_state="No tool lifecycle events observed yet.",
    )
