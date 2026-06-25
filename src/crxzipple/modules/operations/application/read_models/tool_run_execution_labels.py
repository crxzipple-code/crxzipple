from __future__ import annotations

from datetime import datetime

from crxzipple.modules.operations.application.read_models.presenters import (
    title_label,
)
from crxzipple.modules.operations.application.read_models.tool_metric_values import (
    duration_label,
)
from crxzipple.modules.operations.application.read_models.tool_run_time import (
    tool_run_duration_seconds,
)
from crxzipple.modules.tool.domain import Tool, ToolRun, ToolRunAssignment, ToolRunStatus
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc


def assignment_status_label(assignment: ToolRunAssignment | None) -> str:
    if assignment is None:
        return "-"
    return title_label(assignment.status.value)


def assignment_id(assignment: ToolRunAssignment | None) -> str:
    return assignment.id if assignment is not None else "-"


def lease_state_label(
    run: ToolRun,
    *,
    assignment: ToolRunAssignment | None,
    now: datetime,
) -> str:
    if assignment is not None:
        if assignment.lease_expires_at is None:
            return "Released" if assignment.is_terminal() else "-"
        if assignment_lease_expired(assignment, now=now):
            return "Expired"
        return "Active"
    if run.lease_expires_at is None:
        return "Released" if run.is_terminal() else "-"
    if coerce_utc_datetime(run.lease_expires_at) <= coerce_utc_datetime(now):
        return "Expired"
    return "Active"


def lease_expires_label(
    run: ToolRun,
    *,
    assignment: ToolRunAssignment | None,
) -> str:
    value = (
        assignment.lease_expires_at
        if assignment is not None
        else run.lease_expires_at
    )
    return format_datetime_utc(value) if value is not None else "-"


def assignment_lease_expired(
    assignment: ToolRunAssignment,
    *,
    now: datetime,
) -> bool:
    return (
        assignment.lease_expires_at is not None
        and coerce_utc_datetime(assignment.lease_expires_at)
        <= coerce_utc_datetime(now)
    )


def run_duration_label(
    run: ToolRun,
    *,
    assignment: ToolRunAssignment | None = None,
    now: datetime,
) -> str:
    return duration_label(tool_run_duration_seconds(run, assignment=assignment, now=now))


def run_progress_label(
    run: ToolRun,
    *,
    tool: Tool | None,
    assignment: ToolRunAssignment | None,
    now: datetime,
) -> str:
    return f"{run_progress_percent(run, tool=tool, assignment=assignment, now=now)}%"


def run_progress_percent(
    run: ToolRun,
    *,
    tool: Tool | None,
    assignment: ToolRunAssignment | None,
    now: datetime,
) -> int:
    if run.status is ToolRunStatus.SUCCEEDED:
        return 100
    if run.status in {
        ToolRunStatus.FAILED,
        ToolRunStatus.CANCELLED,
        ToolRunStatus.TIMED_OUT,
    }:
        return 100
    if run.status is ToolRunStatus.CREATED:
        return 0
    if run.status is ToolRunStatus.QUEUED:
        return 5
    if run.status is ToolRunStatus.DISPATCHING:
        return 15
    if run.status is ToolRunStatus.CANCEL_REQUESTED:
        return 95
    timeout = max(
        int(tool.execution_policy.timeout_seconds) if tool is not None else 30,
        1,
    )
    elapsed = tool_run_duration_seconds(run, assignment=assignment, now=now)
    return min(95, max(20, int(round((elapsed / timeout) * 100))))
