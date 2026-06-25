from __future__ import annotations

from datetime import datetime

from crxzipple.modules.dispatch.domain import DispatchTask, DispatchTaskStatus
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
)
from crxzipple.modules.operations.application.read_models.presenters import (
    display_value,
    truncate_text,
)
from crxzipple.modules.operations.application.read_models.routes import (
    workbench_trace_route,
)
from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationIngressStatus,
    OrchestrationRunStatus,
)
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc


def columns(*items: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(
        OperationsTableColumnModel(key=key, label=label) for key, label in items
    )


def dispatch_queued_at(task: DispatchTask | None) -> datetime | None:
    if task is None:
        return None
    return task.queued_at or task.created_at


def dispatch_worker(task: DispatchTask | None) -> str:
    if task is None:
        return "-"
    return display(task.claimed_by)


def dispatch_lease_expires_at(task: DispatchTask | None) -> str:
    if task is None or task.lease_expires_at is None:
        return "-"
    return format_datetime_utc(task.lease_expires_at)


def tone_for_ingress_status(status: OrchestrationIngressStatus) -> str:
    if status is OrchestrationIngressStatus.FAILED:
        return "danger"
    if status is OrchestrationIngressStatus.COMPLETED:
        return "success"
    if status is OrchestrationIngressStatus.PROCESSING:
        return "info"
    return "neutral"


def tone_for_dispatch_or_ingress_status(
    dispatch_task: DispatchTask | None,
    ingress_status: OrchestrationIngressStatus,
) -> str:
    if dispatch_task is None:
        return tone_for_ingress_status(ingress_status)
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


def trace_route_from_id(trace_id_value: str | None) -> str:
    return workbench_trace_route(trace_id_value)


def workbench_route(run: OrchestrationRun) -> str:
    return f"/ui/workbench/runs/{run.id}"


def run_summary(run: OrchestrationRun) -> str:
    content = run.inbound_instruction.content
    if content is None:
        return "-"
    if isinstance(content, str):
        return truncate(content)
    return truncate(str(content))


def display(value: object | None) -> str:
    return display_value(value)


def truncate(value: str, *, limit: int = 96) -> str:
    return truncate_text(value, limit)


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
