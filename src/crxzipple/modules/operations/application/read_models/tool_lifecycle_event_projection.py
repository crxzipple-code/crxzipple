from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
)
from crxzipple.modules.operations.application.read_models.presenters import (
    display_value,
    truncate_text,
)
from crxzipple.modules.tool.domain import Tool, ToolRun


def tool_lifecycle_display_priority(event_name: str) -> int:
    normalized = event_name.strip().lower()
    if normalized.startswith(("tool.run.", "tool.assignment.", "tool.worker.")):
        return 0
    if normalized.startswith(("tool.source.", "tool.function.")):
        return 1
    return 2


def tool_lookup(tools: list[Tool]) -> dict[str, Tool]:
    return {tool.id: tool for tool in tools}


def tool_label_from_id(
    tool_id: str | None,
    tools_by_id: dict[str, Tool],
) -> str:
    if tool_id is None:
        return "-"
    tool = tools_by_id.get(tool_id)
    if tool is None:
        return tool_id
    return tool.id if tool.id == tool.name else f"{tool.name} ({tool.id})"


def tool_event_trace_id(
    event: OperationsObservedEvent,
    run: ToolRun | None,
) -> str | None:
    if event.trace_id:
        return event.trace_id
    if run is None:
        return None
    return context_str(run, "trace_id") or context_str(run, "correlation_id")


def short_tool_event_name(event_name: str) -> str:
    return event_name.removeprefix("tool.")


def tool_event_details(payload: dict[str, Any]) -> str:
    keys = (
        "error_message",
        "reason",
        "terminal_reason",
        "attempt_count",
        "mode",
        "strategy",
        "environment",
        "assignment_id",
        "worker_id",
        "previous_status",
        "max_in_flight",
        "current_in_flight",
        "retention_seconds",
    )
    parts = [
        f"{key}={display(payload.get(key))}"
        for key in keys
        if display(payload.get(key)) != "-"
    ]
    return truncate_text(", ".join(parts), 128) if parts else "-"


def tool_event_tone(event: OperationsObservedEvent) -> str:
    status = event.status.lower()
    level = event.level.lower()
    if level == "error" or status in {"failed", "timed-out", "timed_out"}:
        return "danger"
    if level == "warning" or status in {
        "cancelled",
        "cancel-requested",
        "cancel_requested",
        "expired",
        "requeued",
        "stale",
    }:
        return "warning"
    if status in {"succeeded", "created", "queued", "started", "running"}:
        return "success"
    return "info"


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


def tool_label(run: ToolRun, tools_by_id: dict[str, Tool]) -> str:
    tool = tools_by_id.get(run.tool_id)
    if tool is None:
        return run.tool_id
    return tool.id if tool.id == tool.name else f"{tool.name} ({tool.id})"


def columns(*items: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(
        OperationsTableColumnModel(key=column_id, label=label)
        for column_id, label in items
    )


def optional_str(value: object | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def display(value: object | None) -> str:
    return display_value(value)
