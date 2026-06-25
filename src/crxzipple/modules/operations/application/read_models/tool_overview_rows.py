from __future__ import annotations

from datetime import datetime

from crxzipple.modules.operations.application.read_models.presenters import (
    truncate_text,
)
from crxzipple.modules.operations.application.read_models.tool_metric_values import (
    duration_label,
)
from crxzipple.modules.operations.application.read_models.tool_overview_risk import (
    overview_risky_tools,
    tool_risk_reason,
)
from crxzipple.modules.tool.domain import (
    Tool,
    ToolRun,
    ToolRunAssignment,
    ToolRunAssignmentStatus,
    ToolRunStatus,
    ToolWorkerRegistration,
)
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc


def queue_rows(
    runs: list[ToolRun],
    *,
    now: datetime,
    assignment_by_run: dict[str, ToolRunAssignment] | None = None,
) -> tuple[dict[str, str], ...]:
    assignment_by_run = assignment_by_run or {}
    sorted_runs = sorted(runs, key=lambda run: run.created_at)
    return tuple(
        {
            "Priority": run.target.mode.value,
            "Run ID": run.id,
            "Lane Key": run.tool_id,
            "Wait Reason": run_reason(
                run,
                assignment=assignment_by_run.get(run.id),
                now=now,
            ),
            "Wait Time": age_label(run.created_at, now=now),
        }
        for run in sorted_runs[:20]
    )


def risk_rows(tools: list[Tool]) -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "Lane Key": tool.id,
            "Holder Run ID": "-",
            "TTL": f"{tool.execution_policy.timeout_seconds}s",
            "Expires At": "-",
            "Reason": tool_risk_reason(tool),
        }
        for tool in sorted(overview_risky_tools(tools), key=lambda item: item.id)[:20]
    )


def worker_rows(
    workers: list[ToolWorkerRegistration],
    *,
    active_runs: list[ToolRun],
) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    if workers:
        current_run_by_worker = {
            run.worker_id: run.id
            for run in active_runs
            if run.worker_id is not None and run.worker_id.strip()
        }
        for worker in sorted(workers, key=lambda item: item.id):
            rows.append(
                {
                    "Worker ID": worker.id,
                    "Status": worker.status.value,
                    "Last Heartbeat": format_datetime_utc(worker.heartbeat_at),
                    "Current Run": current_run_by_worker.get(worker.id, "-"),
                    "Load": f"{worker.current_in_flight}/{worker.max_in_flight}",
                },
            )
        return tuple(rows[:20])
    for run in sorted(active_runs, key=lambda item: item.created_at, reverse=True):
        rows.append(
            {
                "Worker ID": run.worker_id or "-",
                "Status": run.status.value,
                "Last Heartbeat": (
                    format_datetime_utc(run.heartbeat_at)
                    if run.heartbeat_at is not None
                    else "-"
                ),
                "Current Run": run.id,
                "Load": "-",
            },
        )
    return tuple(rows[:20])


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


def age_label(value: datetime | None, *, now: datetime) -> str:
    if value is None:
        return "-"
    seconds = max(
        int((coerce_utc_datetime(now) - coerce_utc_datetime(value)).total_seconds()),
        0,
    )
    return duration_label(seconds)
