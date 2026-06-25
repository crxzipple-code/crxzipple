from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.orchestration.domain import (
    ExecutionStep,
    ExecutionStepItem,
    OrchestrationRun,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    ExecutionStepItemStatus,
    ExecutionStepStatus,
    OrchestrationRunStatus,
)


def enum_value(value: Any) -> str | None:
    if value is None:
        return None
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        return enum_value
    text = str(value).strip()
    return text or None


def execution_step_view_status(
    step: ExecutionStep,
    *,
    run: OrchestrationRun,
) -> str:
    if step.status is ExecutionStepStatus.COMPLETED:
        return "success"
    if step.status is ExecutionStepStatus.FAILED:
        return "failed"
    if step.status is ExecutionStepStatus.CANCELLED:
        return "cancelled"
    if step.status is ExecutionStepStatus.WAITING:
        return "waiting"
    if step.status is ExecutionStepStatus.RUNNING:
        return "running"
    if run.status in {OrchestrationRunStatus.ACCEPTED, OrchestrationRunStatus.QUEUED}:
        return "queued"
    return "running"


def execution_item_view_status(item: ExecutionStepItem) -> str:
    if item.status is ExecutionStepItemStatus.COMPLETED:
        return "success"
    if item.status is ExecutionStepItemStatus.FAILED:
        return "failed"
    if item.status is ExecutionStepItemStatus.CANCELLED:
        return "cancelled"
    if item.status is ExecutionStepItemStatus.WAITING:
        return "waiting"
    if item.status is ExecutionStepItemStatus.RUNNING:
        return "running"
    if item.status in {
        ExecutionStepItemStatus.LATE_OBSERVED,
        ExecutionStepItemStatus.LATE_IGNORED,
    }:
        return "success"
    return "queued"


def llm_invocation_llm_id(invocation: Any | None) -> str | None:
    if invocation is None:
        return None
    return optional_text(getattr(invocation, "llm_id", None))


def llm_started_at(run: OrchestrationRun, invocation: Any | None) -> datetime | None:
    return getattr(invocation, "started_at", None) or run.started_at or run.updated_at


def llm_completed_at(run: OrchestrationRun, invocation: Any | None) -> datetime | None:
    return getattr(invocation, "completed_at", None) or run.updated_at


def optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
