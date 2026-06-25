from __future__ import annotations

from collections import Counter
from datetime import datetime

from crxzipple.modules.dispatch.domain import DispatchTask
from crxzipple.modules.orchestration.domain import (
    ExecutionStep,
    ExecutionStepItem,
    OrchestrationRun,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    ExecutionChainStatus,
)
from crxzipple.modules.operations.application.read_models.presenters import (
    display_value,
)
from crxzipple.modules.operations.application.read_models.routes import (
    workbench_trace_route,
)
from crxzipple.shared.time import coerce_utc_datetime


def execution_step_label(step: ExecutionStep | None) -> str:
    if step is None:
        return "-"
    return f"{step.step_index}:{step.kind.value}/{step.status.value}"


def execution_step_breakdown(steps: list[ExecutionStep]) -> str:
    if not steps:
        return "-"
    return "; ".join(
        execution_step_label(step)
        for step in sorted(steps, key=lambda item: item.step_index)[:12]
    )


def execution_item_breakdown(items: list[ExecutionStepItem]) -> str:
    if not items:
        return "-"
    counts: Counter[str] = Counter(
        f"{item.kind.value}:{item.status.value}" for item in items
    )
    return " / ".join(f"{count} {key}" for key, count in sorted(counts.items()))


def tone_for_execution_chain_status(status: ExecutionChainStatus) -> str:
    if status is ExecutionChainStatus.FAILED:
        return "danger"
    if status is ExecutionChainStatus.WAITING:
        return "warning"
    if status is ExecutionChainStatus.RUNNING:
        return "info"
    if status is ExecutionChainStatus.COMPLETED:
        return "success"
    return "neutral"


def dispatch_worker(task: DispatchTask | None) -> str:
    if task is None:
        return "-"
    return display_value(task.claimed_by)


def trace_id(run: OrchestrationRun) -> str:
    trace = run.metadata.get("trace_id")
    if isinstance(trace, str) and trace.strip():
        return trace.strip()
    correlation_id = run.metadata.get("correlation_id")
    if isinstance(correlation_id, str) and correlation_id.strip():
        return correlation_id.strip()
    return run.id


def trace_route(run: OrchestrationRun) -> str:
    return workbench_trace_route(trace_id(run))


def workbench_route(run: OrchestrationRun) -> str:
    return f"/ui/workbench/runs/{run.id}"


def age_label(value: datetime | None, *, now: datetime) -> str:
    if value is None:
        return "-"
    return _duration_label(_age_seconds(value, now=now))


def _age_seconds(value: datetime | None, *, now: datetime) -> int:
    if value is None:
        return 0
    return max(
        int((coerce_utc_datetime(now) - coerce_utc_datetime(value)).total_seconds()),
        0,
    )


def _duration_label(seconds: int) -> str:
    seconds = max(seconds, 0)
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"
