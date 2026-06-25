from __future__ import annotations

from typing import Mapping

from crxzipple.modules.operations.application.read_models.routes import (
    normalize_workbench_trace_route,
    workbench_trace_route,
)
from crxzipple.modules.tool.domain import ToolRun


def tool_run_trace_id(
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


def tool_run_trace_route(
    run: ToolRun,
    *,
    run_context: Mapping[str, str] | None = None,
) -> str:
    route = context_value(run_context, "trace_route", blank_as_none=True)
    if route:
        return normalize_workbench_trace_route(route)
    return workbench_trace_route(tool_run_trace_id(run, run_context=run_context))


def tool_run_source_label(
    run: ToolRun,
    *,
    run_context: Mapping[str, str] | None = None,
) -> str:
    run_id = tool_run_orchestration_run_id(run, run_context=run_context)
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


def tool_run_source_route(
    run: ToolRun,
    *,
    run_context: Mapping[str, str] | None = None,
) -> str:
    route = context_value(run_context, "route", blank_as_none=True)
    if route:
        return route
    run_id = tool_run_orchestration_run_id(run, run_context=run_context)
    return f"/ui/workbench/runs/{run_id}" if run_id else "-"


def tool_run_orchestration_run_id(
    run: ToolRun,
    *,
    run_context: Mapping[str, str] | None = None,
) -> str | None:
    return (
        context_value(run_context, "run_id", blank_as_none=True)
        or metadata_str(run, "orchestration_run_id")
        or context_str(run, "run_id")
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
    if value is None:
        return None if blank_as_none else "-"
    normalized = str(value).strip()
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
