from __future__ import annotations

from crxzipple.modules.workbench.application import view_models as models
from typing import Any

from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.orchestration.domain.value_objects import (
    ExecutionStepItemKind,
    ExecutionStepKind,
    ExecutionStepStatus,
    OrchestrationRunStatus,
)
from crxzipple.modules.workbench.application.execution_projection import (
    execution_item_summary,
    execution_step_view_status,
)
from crxzipple.modules.workbench.application.projection_helpers import optional_text
from crxzipple.modules.workbench.application.run_status_projection import (
    pending_approval,
)
from crxzipple.modules.workbench.application.step_detail_projection import (
    approval_detail as approval_detail_from_payload,
    approval_entities,
    approval_summary,
    failure_guidance_markdown,
    missing_access_entities,
    missing_access_summary,
)
from crxzipple.modules.workbench.application.step_view_factory import make_step_view


def missing_access_step_view(
    run: OrchestrationRun,
    *,
    turn_id: str,
    access_payload: dict[str, object],
) -> Any:
    return make_step_view(
        run=run,
        turn_id=turn_id,
        step_id="missing_access",
        step_type="missing_access",
        status=(
            "waiting"
            if run.status is OrchestrationRunStatus.WAITING
            else "failed"
        ),
        title="External Access Required",
        summary=missing_access_summary(access_payload),
        markdown=failure_guidance_markdown(
            message=run.error.message if run.error is not None else "External access is not ready.",
            code=run.error.code if run.error is not None else "access_not_ready",
            details=access_payload,
        ),
        started_at=run.completed_at or run.updated_at,
        completed_at=run.completed_at,
        badges=(models.StatusBadgeModel(label="Access", tone="warning"),),
        linked_entities=missing_access_entities(access_payload),
    )


def chain_approval_step_view(
    run: OrchestrationRun,
    *,
    turn_id: str,
    bundle: Any,
) -> Any | None:
    approval_item = next(
        (
            item
            for item in bundle.items
            if item.kind is ExecutionStepItemKind.APPROVAL_REQUEST
        ),
        None,
    )
    payload = (
        execution_item_summary(approval_item)
        if approval_item is not None
        else pending_approval(run)
    )
    if not payload:
        return None
    request_id = optional_text(payload.get("request_id")) or optional_text(
        payload.get("id"),
    )
    approval_detail = approval_detail_from_payload(payload)
    return make_step_view(
        run=run,
        turn_id=turn_id,
        step_id=f"execution:{bundle.step.id}",
        step_type="approval_required",
        status=execution_step_view_status(bundle.step, run=run),
        title="Approval Required",
        summary=approval_summary(payload),
        started_at=bundle.step.started_at or bundle.step.created_at,
        completed_at=bundle.step.completed_at,
        badges=(models.StatusBadgeModel(label="Authorization", tone="warning"),),
        linked_entities=approval_entities(approval_detail),
        approval=approval_detail,
        approval_request_id=request_id,
        trace_step_id=bundle.step.id,
    )


def generic_execution_step_view(
    run: OrchestrationRun,
    *,
    turn_id: str,
    bundle: Any,
) -> Any:
    step = bundle.step
    if step.kind is ExecutionStepKind.ERROR or step.status is ExecutionStepStatus.FAILED:
        step_type = "error"
        title = "Run Failed"
        summary = (
            step.error_payload.message
            if step.error_payload is not None
            else run.error.message
            if run.error is not None
            else "Run failed."
        )
        error_code = (
            step.error_payload.code
            if step.error_payload is not None
            else run.error.code
            if run.error is not None
            else None
        )
        error_details = (
            step.error_payload.details
            if step.error_payload is not None
            else run.error.details
            if run.error is not None
            else None
        )
        markdown = failure_guidance_markdown(
            message=summary,
            code=error_code,
            details=error_details,
        )
    else:
        step_type = "agent_thinking"
        title = step.kind.value.replace("_", " ").title()
        summary = f"Execution step: {step.kind.value}."
        markdown = None
    return make_step_view(
        run=run,
        turn_id=turn_id,
        step_id=f"execution:{step.id}",
        step_type=step_type,
        status=execution_step_view_status(step, run=run),
        title=title,
        summary=summary,
        markdown=markdown,
        started_at=step.started_at or step.created_at,
        completed_at=step.completed_at,
        trace_step_id=step.id,
    )
