from __future__ import annotations

from datetime import datetime

from crxzipple.modules.operations.application.read_models.presenters import title_label
from crxzipple.modules.operations.application.read_models.routes import (
    workbench_trace_route,
)
from crxzipple.modules.tool.domain import Tool, ToolRun, ToolRunAssignment
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


def source_label(run: ToolRun) -> str:
    run_id = orchestration_run_id(run)
    tool_call_id = metadata_str(run, "tool_call_id")
    step_id = context_str(run, "step_id")
    turn_id = context_str(run, "turn_id")
    if run_id and tool_call_id:
        return f"{run_id} / {tool_call_id}"
    if run_id and step_id:
        return f"{run_id} / {step_id}"
    if run_id and turn_id:
        return f"{run_id} / {turn_id}"
    return run_id or turn_id or "-"


def source_route(run: ToolRun) -> str:
    run_id = orchestration_run_id(run)
    return f"/ui/workbench/runs/{run_id}" if run_id else "-"


def trace_id(run: ToolRun) -> str:
    return (
        context_str(run, "trace_id")
        or context_str(run, "correlation_id")
        or metadata_str(run, "orchestration_run_id")
        or context_str(run, "run_id")
        or run.id
    )


def trace_route(run: ToolRun) -> str:
    return workbench_trace_route(trace_id(run))


def orchestration_run_id(run: ToolRun) -> str | None:
    return metadata_str(run, "orchestration_run_id") or context_str(run, "run_id")


def context_str(run: ToolRun, key: str) -> str | None:
    context = run.invocation_context
    return context.get_str(key) if context is not None else None


def metadata_str(run: ToolRun, key: str) -> str | None:
    value = run.metadata.get(key)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def tool_lookup(tools: list[Tool]) -> dict[str, Tool]:
    return {tool.id: tool for tool in tools}


def tool_label(run: ToolRun, tools_by_id: dict[str, Tool]) -> str:
    tool = tools_by_id.get(run.tool_id)
    if tool is None:
        return run.tool_id
    return tool.id if tool.id == tool.name else f"{tool.name} ({tool.id})"
