from __future__ import annotations

from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationRunStage,
    OrchestrationRunStatus,
)
from crxzipple.modules.workbench.application import view_models as models
from crxzipple.modules.workbench.application.run_time_projection import span_ms


def status_strip(run: OrchestrationRun):
    if run.status in {
        OrchestrationRunStatus.COMPLETED,
        OrchestrationRunStatus.CANCELLED,
        OrchestrationRunStatus.FAILED,
    }:
        return None
    label = {
        OrchestrationRunStatus.ACCEPTED: "Accepted",
        OrchestrationRunStatus.QUEUED: "Queued for execution",
        OrchestrationRunStatus.RUNNING: f"Running: {run.stage.value}",
        OrchestrationRunStatus.WAITING: run.waiting_reason or "Waiting",
    }.get(run.status, run.status.value)
    return models.RunStatusStrip(
        label=label,
        eta_ms=None,
        queue_wait_ms=span_ms(run.queued_at, run.started_at or run.updated_at) or 0,
    )


def pending_approval(run: OrchestrationRun) -> dict[str, object] | None:
    if not run_is_waiting_for_approval(run):
        return None
    return (
        dict(run.pending_approval_request_payload)
        if run.pending_approval_request_payload is not None
        else None
    )


def run_is_waiting_for_approval(run: OrchestrationRun) -> bool:
    return (
        run.status is OrchestrationRunStatus.WAITING
        and run.stage is OrchestrationRunStage.WAITING_FOR_CONFIRMATION
    )
