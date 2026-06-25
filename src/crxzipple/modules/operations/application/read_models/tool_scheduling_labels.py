from __future__ import annotations

from datetime import datetime

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
)
from crxzipple.modules.operations.application.read_models.presenters import (
    title_label,
    truncate_text,
)
from crxzipple.modules.operations.application.read_models.tool_metric_values import (
    duration_label,
)
from crxzipple.modules.tool.domain import (
    ToolRun,
    ToolRunAssignment,
    ToolRunAssignmentStatus,
    ToolRunStatus,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_run_projection import (
    assignment_lease_expired,
    context_str,
)
from crxzipple.shared.time import coerce_utc_datetime


def capability_label(group_key: str) -> str:
    if group_key == "tool:*":
        return "Default tool groups"
    if group_key.startswith("tool:"):
        return group_key.removeprefix("tool:")
    if group_key == "capability:image":
        return "Image generation"
    if group_key == "capability:browser":
        return "Browser shared state"
    if group_key == "capability:workspace":
        return "Workspace shared state"
    if group_key == "capability:mobile":
        return "Mobile shared state"
    if group_key == "capability:session":
        return "Session shared state"
    if group_key == "capability:command":
        return "Command shared state"
    if group_key == "capability:system":
        return "System shared state"
    return title_label(group_key.removeprefix("capability:"))


def run_reason(
    run: ToolRun,
    *,
    assignment: ToolRunAssignment | None = None,
    now: datetime | None = None,
) -> str:
    if run.error_message:
        return truncate_text(run.error_message, 64)
    if assignment is not None and not assignment.is_terminal():
        if now is not None and assignment_lease_expired(assignment, now=now):
            return "assignment lease expired"
        if assignment.status is ToolRunAssignmentStatus.ASSIGNED:
            return "assigned to worker"
        if assignment.status is ToolRunAssignmentStatus.RUNNING:
            return "running on worker"
    if run.status is ToolRunStatus.CANCEL_REQUESTED:
        return "cancel requested"
    if run.status is ToolRunStatus.DISPATCHING:
        return "dispatching to worker"
    if (
        run.status in {ToolRunStatus.DISPATCHING, ToolRunStatus.RUNNING}
        and run.worker_id
        and assignment is None
    ):
        return "worker assignment missing"
    if run.status is ToolRunStatus.CREATED:
        return "created"
    if run.status is ToolRunStatus.RUNNING:
        return "running"
    return run.status.value


def retry_budget_label(run: ToolRun) -> str:
    remaining = max(run.max_attempts - run.attempt_count, 0)
    return f"{remaining} left ({run.attempt_count}/{run.max_attempts})"


def run_priority_label(run: ToolRun) -> str:
    for key in ("priority", "run_priority", "queue_priority"):
        value = context_str(run, key)
        if value:
            return value
    return "-"


def is_waiting_io_reason(reason: str) -> bool:
    normalized = reason.lower()
    return any(
        token in normalized
        for token in (
            "provider",
            "limiter",
            "rate",
            "capability capacity",
            "external",
            "io",
        )
    )


def queue_oldest_label(
    runs: list[ToolRun],
    *,
    assignment_by_run: dict[str, ToolRunAssignment],
    now: datetime,
) -> str:
    starts: list[datetime] = []
    for run in runs:
        assignment = assignment_by_run.get(run.id)
        if assignment is not None and not assignment.is_terminal():
            starts.append(assignment.started_at or assignment.assigned_at)
            continue
        starts.append(run.created_at)
    return age_label(min(starts), now=now) if starts else "-"


def queue_reason_tone(reason: str) -> str:
    normalized = reason.lower()
    if "expired" in normalized or "missing" in normalized:
        return "danger"
    if "inline" in normalized or "running" in normalized:
        return "info"
    if "queued" in normalized or "cancel" in normalized:
        return "warning"
    return "neutral"


def age_label(value: datetime | None, *, now: datetime) -> str:
    if value is None:
        return "-"
    seconds = max(
        int((coerce_utc_datetime(now) - coerce_utc_datetime(value)).total_seconds()),
        0,
    )
    return duration_label(seconds)


def percent_label(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0%"
    return f"{round((numerator / denominator) * 100)}%"


def columns(*items: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(
        OperationsTableColumnModel(key=key, label=label) for key, label in items
    )
