from __future__ import annotations

from datetime import datetime
from typing import Mapping

from crxzipple.modules.operations.application.read_models.presenters import (
    title_label,
)
from crxzipple.modules.operations.application.read_models.routes import (
    normalize_workbench_trace_route,
    workbench_trace_route,
)
from crxzipple.modules.tool.domain import (
    Tool,
    ToolRun,
    ToolRunAssignment,
    ToolRunStatus,
)
from crxzipple.shared.time import coerce_utc_datetime


def latest_assignment_by_run(
    assignments: list[ToolRunAssignment],
) -> dict[str, ToolRunAssignment]:
    latest: dict[str, ToolRunAssignment] = {}
    for assignment in sorted(
        assignments,
        key=lambda item: item.assigned_at,
        reverse=True,
    ):
        latest.setdefault(assignment.run_id, assignment)
    return latest


def assignment_id(assignment: ToolRunAssignment | None) -> str:
    return assignment.id if assignment is not None else "-"


def lease_state_label(
    run: ToolRun,
    *,
    assignment: ToolRunAssignment | None,
    now: datetime,
) -> str:
    if assignment is not None and not assignment.is_terminal():
        if assignment_lease_expired(assignment, now=now):
            return "Lease Expired"
        return title_label(assignment.status.value)
    if run.lease_expires_at is not None and coerce_utc_datetime(
        run.lease_expires_at,
    ) < coerce_utc_datetime(now):
        return "Lease Expired"
    return title_label(run.status.value)


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


def source_label(
    run: ToolRun,
    *,
    run_context: Mapping[str, str] | None = None,
) -> str:
    run_id = orchestration_run_id(run, run_context=run_context)
    tool_call_id = (
        context_value(run_context, "tool_call_id", blank_as_none=True)
        or metadata_str(run, "tool_call_id")
    )
    step_id = context_value(
        run_context,
        "step_id",
        blank_as_none=True,
    ) or context_str(run, "step_id")
    turn_id = context_value(
        run_context,
        "turn_id",
        blank_as_none=True,
    ) or context_str(run, "turn_id")
    if run_id and tool_call_id:
        return f"{run_id} / {tool_call_id}"
    if run_id and step_id:
        return f"{run_id} / {step_id}"
    if run_id and turn_id:
        return f"{run_id} / {turn_id}"
    return run_id or turn_id or "-"


def trace_id(
    run: ToolRun,
    *,
    run_context: Mapping[str, str] | None = None,
) -> str:
    return (
        context_value(run_context, "trace_id", blank_as_none=True)
        or context_str(run, "trace_id")
        or context_str(run, "correlation_id")
        or metadata_str(run, "orchestration_run_id")
        or context_str(run, "run_id")
        or run.id
    )


def trace_route(
    run: ToolRun,
    *,
    run_context: Mapping[str, str] | None = None,
) -> str:
    route = context_value(run_context, "trace_route", blank_as_none=True)
    if route:
        return normalize_workbench_trace_route(route)
    return workbench_trace_route(trace_id(run, run_context=run_context))


def orchestration_run_id(
    run: ToolRun,
    *,
    run_context: Mapping[str, str] | None = None,
) -> str | None:
    return (
        context_value(run_context, "run_id", blank_as_none=True)
        or context_str(run, "orchestration_run_id")
        or context_str(run, "turn_id")
        or metadata_str(run, "orchestration_run_id")
        or metadata_str(run, "turn_id")
    )


def context_value(
    run_context: Mapping[str, str] | None,
    key: str,
    *,
    blank_as_none: bool = False,
) -> str | None:
    if run_context is None:
        return None if blank_as_none else "-"
    value = run_context.get(key)
    normalized = str(value or "").strip()
    if not normalized or normalized == "-":
        return None if blank_as_none else "-"
    return normalized


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


def tool_run_tone(status: ToolRunStatus) -> str:
    if status is ToolRunStatus.SUCCEEDED:
        return "success"
    if status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}:
        return "danger"
    if status in {ToolRunStatus.CANCEL_REQUESTED, ToolRunStatus.CANCELLED}:
        return "warning"
    if status in {ToolRunStatus.RUNNING, ToolRunStatus.DISPATCHING}:
        return "info"
    return "neutral"
