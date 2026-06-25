from __future__ import annotations

from datetime import datetime

from crxzipple.modules.operations.application.read_models.presenters import display_value
from crxzipple.modules.operations.application.read_models.routes import (
    workbench_trace_route,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationExecutorLease,
    OrchestrationRun,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationRunStage,
    OrchestrationRunStatus,
)
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc


def run_type_label(run: OrchestrationRun) -> str:
    if run.stage in {
        OrchestrationRunStage.TOOL,
        OrchestrationRunStage.WAITING_ON_TOOL,
    }:
        return "tool.call"
    return "agent.run"


def run_progress_label(run: OrchestrationRun) -> str:
    if run.status is OrchestrationRunStatus.COMPLETED:
        return "100%"
    if run.max_steps <= 0:
        return "-"
    return f"{min(round((run.current_step / run.max_steps) * 100), 99)}%"


def lane_lock_ttl_label(
    lease: OrchestrationExecutorLease | None,
    *,
    now: datetime,
) -> str:
    if lease is None or lease.lease_expires_at is None:
        return "lease-bound"
    remaining_seconds = int(
        (
            coerce_utc_datetime(lease.lease_expires_at) - coerce_utc_datetime(now)
        ).total_seconds(),
    )
    if remaining_seconds <= 0:
        return "expired"
    return duration_label(remaining_seconds)


def lane_lock_expires_label(lease: OrchestrationExecutorLease | None) -> str:
    if lease is None or lease.lease_expires_at is None:
        return "-"
    return format_datetime_utc(lease.lease_expires_at)


def lane_lock_renewed_at(
    run: OrchestrationRun,
    lease: OrchestrationExecutorLease | None,
) -> datetime:
    if lease is None:
        return run.updated_at
    return max(
        coerce_utc_datetime(run.updated_at),
        coerce_utc_datetime(lease.last_heartbeat_at),
    )


def tone_for_executor_status(status: str) -> str:
    if status == "online":
        return "success"
    if status == "draining":
        return "warning"
    if status == "offline":
        return "danger"
    return "neutral"


def trace_id(run: OrchestrationRun) -> str:
    metadata_trace_id = run.metadata.get("trace_id")
    if isinstance(metadata_trace_id, str) and metadata_trace_id.strip():
        return metadata_trace_id.strip()
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


def age_label(value: datetime | None, *, now: datetime) -> str:
    if value is None:
        return "-"
    return duration_label(age_seconds(value, now=now))
