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
from crxzipple.modules.tool.domain import ToolRun, ToolRunAssignment, ToolRunStatus
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc


def worker_success_rate_label(worker_id: str, *, runs: list[ToolRun]) -> str:
    terminal_runs = [
        run
        for run in runs
        if run.worker_id == worker_id and run.is_terminal()
    ]
    if not terminal_runs:
        return "-"
    successes = sum(1 for run in terminal_runs if run.status is ToolRunStatus.SUCCEEDED)
    return percent_label(successes, len(terminal_runs))


def worker_avg_duration_label(
    worker_id: str,
    *,
    runs: list[ToolRun],
    assignment_by_run: dict[str, ToolRunAssignment],
    now: datetime,
) -> str:
    durations = [
        tool_run_duration_seconds(run, assignment=assignment_by_run.get(run.id), now=now)
        for run in runs
        if run.worker_id == worker_id and run.is_terminal()
    ]
    if not durations:
        return "-"
    return duration_label(int(round(sum(durations) / len(durations))))


def worker_run_bucket(run: ToolRun, *, now: datetime) -> str:
    if (
        run.status
        in {
            ToolRunStatus.DISPATCHING,
            ToolRunStatus.RUNNING,
            ToolRunStatus.CANCEL_REQUESTED,
        }
        and run.lease_expires_at is not None
        and coerce_utc_datetime(run.lease_expires_at) < coerce_utc_datetime(now)
    ):
        return "lease_expired"
    return run.status.value


def worker_run_status_label(status: ToolRunStatus) -> str:
    return title_label(status.value)


def worker_run_tone(status: ToolRunStatus) -> str:
    if status is ToolRunStatus.SUCCEEDED:
        return "success"
    if status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}:
        return "danger"
    if status in {ToolRunStatus.CANCEL_REQUESTED, ToolRunStatus.CANCELLED}:
        return "warning"
    if status in {ToolRunStatus.RUNNING, ToolRunStatus.DISPATCHING}:
        return "info"
    return "neutral"


def worker_run_lease_expires_label(run: ToolRun) -> str:
    return format_datetime_utc(run.lease_expires_at) if run.lease_expires_at else "-"


def percent_label(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0%"
    return f"{round((numerator / denominator) * 100)}%"
