from __future__ import annotations

from typing import Any

from crxzipple.modules.workbench.application import view_models as models
from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.orchestration.domain.value_objects import OrchestrationRunStatus
from crxzipple.modules.workbench.application.run_status_projection import (
    pending_approval,
)
from crxzipple.modules.workbench.application.run_text_projection import (
    output_text as run_output_text,
)
from crxzipple.modules.workbench.application.step_detail_projection import (
    approval_detail as approval_detail_from_payload,
    approval_entities,
    approval_summary,
    failure_guidance_markdown,
    missing_access_payload,
)
from crxzipple.modules.workbench.application.step_support_views import (
    missing_access_step_view,
)
from crxzipple.modules.workbench.application.step_view_factory import make_step_view


def append_access_and_approval_steps(
    steps: list[Any],
    *,
    run: OrchestrationRun,
    turn_id: str,
) -> None:
    access_payload = missing_access_payload(run)
    if access_payload is not None:
        steps.append(
            missing_access_step_view(
                run=run,
                turn_id=turn_id,
                access_payload=access_payload,
            ),
        )

    approval = pending_approval(run)
    if approval is None:
        return
    request_id = str(approval.get("request_id") or approval.get("id") or "")
    approval_detail = approval_detail_from_payload(approval)
    steps.append(
        make_step_view(
            run=run,
            turn_id=turn_id,
            step_id=f"approval_{request_id or 'pending'}",
            step_type="approval_required",
            status="waiting",
            title="Approval Required",
            summary=approval_summary(approval),
            started_at=run.updated_at,
            completed_at=None,
            badges=(
                models.StatusBadgeModel(
                    label="Authorization",
                    tone="warning",
                ),
            ),
            linked_entities=approval_entities(approval_detail),
            approval=approval_detail,
            approval_request_id=request_id or None,
        ),
    )


def append_terminal_step(
    steps: list[Any],
    *,
    run: OrchestrationRun,
    turn_id: str,
) -> None:
    access_payload = missing_access_payload(run)
    if run.status is OrchestrationRunStatus.COMPLETED:
        final_output_text = run_output_text(run)
        steps.append(
            make_step_view(
                run=run,
                turn_id=turn_id,
                step_id="final_response",
                step_type="final_response",
                status="success",
                title="Final Response",
                summary=final_output_text or "Run completed.",
                markdown=final_output_text,
                started_at=run.completed_at or run.updated_at,
                completed_at=run.completed_at or run.updated_at,
            ),
        )
    elif run.status is OrchestrationRunStatus.FAILED and access_payload is None:
        failure_message = run.error.message if run.error is not None else "Run failed."
        steps.append(
            make_step_view(
                run=run,
                turn_id=turn_id,
                step_id="error",
                step_type="error",
                status="failed",
                title="Run Failed",
                summary=failure_message,
                markdown=failure_guidance_markdown(
                    message=failure_message,
                    code=run.error.code if run.error is not None else None,
                    details=run.error.details if run.error is not None else None,
                ),
                started_at=run.completed_at or run.updated_at,
                completed_at=run.completed_at or run.updated_at,
                badges=(
                    models.StatusBadgeModel(
                        label=run.error.code if run.error is not None else "error",
                        tone="danger",
                    ),
                ),
            ),
        )
