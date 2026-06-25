from __future__ import annotations

from datetime import datetime

from crxzipple.modules.tool.domain import (
    ToolRun,
    ToolRunAssignment,
)
from crxzipple.shared.time import coerce_utc_datetime


def tool_run_time(run: ToolRun) -> datetime:
    return run.completed_at or run.heartbeat_at or run.started_at or run.created_at


def tool_run_duration_seconds(
    run: ToolRun,
    *,
    assignment: ToolRunAssignment | None = None,
    now: datetime,
) -> int:
    if assignment is not None:
        start = assignment.started_at or assignment.assigned_at
        end = (
            assignment.completed_at
            if assignment.is_terminal() and assignment.completed_at
            else now
        )
    else:
        start = run.started_at or run.created_at
        end = run.completed_at if run.is_terminal() and run.completed_at else now
    return max(
        int((coerce_utc_datetime(end) - coerce_utc_datetime(start)).total_seconds()),
        0,
    )
