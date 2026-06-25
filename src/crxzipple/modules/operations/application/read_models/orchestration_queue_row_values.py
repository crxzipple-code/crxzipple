from __future__ import annotations

from datetime import datetime

from crxzipple.modules.dispatch.domain import DispatchTask, DispatchTaskStatus
from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationRunStage,
    OrchestrationRunStatus,
)
from crxzipple.modules.operations.application.read_models.presenters import display_value
from crxzipple.modules.operations.application.read_models.routes import (
    workbench_trace_route,
)
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc


def dispatch_queued_at(task: DispatchTask | None) -> datetime | None:
    if task is None:
        return None
    return task.queued_at or task.created_at


def dispatch_wait_reason(task: DispatchTask | None) -> str | None:
    if task is None:
        return None
    if task.waiting_reason is not None and task.waiting_reason.strip():
        return task.waiting_reason.strip()
    return task.policy.value


def dispatch_priority_label(task: DispatchTask | None, fallback: int) -> int:
    return task.priority if task is not None else fallback


def dispatch_worker(task: DispatchTask | None) -> str:
    if task is None:
        return "-"
    return display(task.claimed_by)


def dispatch_lease_expires_at(task: DispatchTask | None) -> str:
    if task is None or task.lease_expires_at is None:
        return "-"
    return format_datetime_utc(task.lease_expires_at)


def run_wait_reason(run: OrchestrationRun) -> str:
    if run.waiting_reason:
        return run.waiting_reason
    if run.stage is OrchestrationRunStage.WAITING_FOR_CONFIRMATION:
        return "Waiting for approval"
    if run.stage is OrchestrationRunStage.WAITING_ON_TOOL:
        return "Waiting for tool"
    if run.lane_key:
        return "Waiting for worker"
    return run.queue_policy.value


def tone_for_dispatch_or_run_status(
    dispatch_task: DispatchTask | None,
    run_status: OrchestrationRunStatus,
) -> str:
    if dispatch_task is None:
        return tone_for_run_status(run_status)
    return tone_for_dispatch_status(dispatch_task.status)


def tone_for_dispatch_status(status: DispatchTaskStatus) -> str:
    if status is DispatchTaskStatus.FAILED:
        return "danger"
    if status is DispatchTaskStatus.CANCELLED:
        return "neutral"
    if status is DispatchTaskStatus.COMPLETED:
        return "success"
    if status is DispatchTaskStatus.CLAIMED:
        return "info"
    if status in {DispatchTaskStatus.QUEUED, DispatchTaskStatus.WAITING}:
        return "warning"
    return "neutral"


def tone_for_run_status(status: OrchestrationRunStatus) -> str:
    if status is OrchestrationRunStatus.FAILED:
        return "danger"
    if status is OrchestrationRunStatus.COMPLETED:
        return "success"
    if status in {
        OrchestrationRunStatus.CANCELLED,
        OrchestrationRunStatus.WAITING,
    }:
        return "warning"
    if status is OrchestrationRunStatus.RUNNING:
        return "info"
    return "neutral"


def trace_id(run: OrchestrationRun) -> str:
    trace_id_value = run.metadata.get("trace_id")
    if isinstance(trace_id_value, str) and trace_id_value.strip():
        return trace_id_value.strip()
    correlation_id = run.metadata.get("correlation_id")
    if isinstance(correlation_id, str) and correlation_id.strip():
        return correlation_id.strip()
    return run.id


def trace_route(run: OrchestrationRun) -> str:
    return workbench_trace_route(trace_id(run))


def workbench_route(run: OrchestrationRun) -> str:
    return f"/ui/workbench/runs/{run.id}"


def display(value: object | None) -> str:
    return display_value(value)


def age_label(value: datetime | None, *, now: datetime) -> str:
    if value is None:
        return "-"
    return duration_label(age_seconds(value, now=now))


def age_seconds(value: datetime | None, *, now: datetime) -> int:
    if value is None:
        return 0
    return max(
        int((coerce_utc_datetime(now) - coerce_utc_datetime(value)).total_seconds()),
        0,
    )


def duration_label(seconds: int) -> str:
    seconds = max(seconds, 0)
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"
