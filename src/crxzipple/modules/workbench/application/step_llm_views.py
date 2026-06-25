from __future__ import annotations

from crxzipple.modules.workbench.application import view_models as models
from typing import Any

from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.orchestration.domain.value_objects import (
    ExecutionStepStatus,
    OrchestrationRunStatus,
)
from crxzipple.modules.workbench.application.execution_projection import (
    execution_step_view_status,
    llm_completed_at,
    llm_invocation_id_from_execution_items,
    llm_invocation_llm_id,
    llm_started_at,
    safe_llm_invocation,
    summary_text_from_items,
    tool_names_from_execution_items,
)
from crxzipple.modules.workbench.application.projection_helpers import (
    metadata_str,
)
from crxzipple.modules.workbench.application.run_llm_projection import (
    llm_id,
    llm_summary,
)
from crxzipple.modules.workbench.application.step_llm_continuation_views import (
    continuation_decision_step_views,
)
from crxzipple.modules.workbench.application.step_llm_progress_views import (
    assistant_progress_step_views,
)
from crxzipple.modules.workbench.application.step_diagnostics import (
    llm_diagnostic_badges,
    llm_diagnostics_sentence,
    llm_step_diagnostics,
    tool_only_streak_badges,
)
from crxzipple.modules.workbench.application.step_detail_projection import (
    failure_guidance_markdown,
)
from crxzipple.modules.workbench.application.step_view_factory import make_step_view


def chain_llm_step_views(
    llm_query: Any | None,
    session_query: Any | None,
    run: OrchestrationRun,
    *,
    turn_id: str,
    bundle: Any,
    tool_only_streak: int = 0,
) -> tuple[Any, ...]:
    return (
        *assistant_progress_step_views(
            session_query,
            run,
            turn_id=turn_id,
            bundle=bundle,
        ),
        _chain_llm_step_view(
            llm_query,
            run,
            turn_id=turn_id,
            bundle=bundle,
            tool_only_streak=tool_only_streak,
        ),
        *continuation_decision_step_views(
            run,
            turn_id=turn_id,
            bundle=bundle,
        ),
    )


def _chain_llm_step_view(
    llm_query: Any | None,
    run: OrchestrationRun,
    *,
    turn_id: str,
    bundle: Any,
    tool_only_streak: int = 0,
) -> Any:
    step = bundle.step
    invocation_id = llm_invocation_id_from_execution_items(bundle.items)
    llm_invocation = safe_llm_invocation(llm_query, invocation_id)
    tool_names = tool_names_from_execution_items(bundle.items)
    is_dispatch_wait = (
        step.status is ExecutionStepStatus.CREATED
        and run.status
        in {OrchestrationRunStatus.ACCEPTED, OrchestrationRunStatus.QUEUED}
    )
    if is_dispatch_wait:
        return make_step_view(
            run=run,
            turn_id=turn_id,
            step_id=f"execution:{step.id}",
            step_type="agent_thinking",
            status="queued",
            title="Queued",
            summary=run.waiting_reason or "Run is waiting for scheduler admission.",
            started_at=run.queued_at or step.created_at,
            completed_at=None,
            trace_step_id=step.id,
        )
    diagnostics = llm_step_diagnostics(llm_invocation, bundle.items)
    request_render_snapshot_id = (
        summary_text_from_items(bundle.items, "request_render_snapshot_id")
        or metadata_str(run, "request_render_snapshot_id")
    )
    step_error = step.error_payload
    summary = (
        step_error.message
        if step_error is not None and step.status is ExecutionStepStatus.FAILED
        else llm_summary(run, llm_invocation=llm_invocation)
    )
    if diagnostics:
        summary = f"{summary} {llm_diagnostics_sentence(diagnostics)}"
    if tool_only_streak >= 3:
        summary = f"{summary} Tool-only streak: {tool_only_streak} LLM steps."
    if llm_invocation is None and tool_names:
        summary = f"{summary} Model requested tool call(s): {', '.join(tool_names)}."
    badge_label = (
        llm_invocation_llm_id(llm_invocation)
        or summary_text_from_items(bundle.items, "llm_id")
        or llm_id(run)
        or "Auto"
    )
    badges = (
        models.StatusBadgeModel(label=badge_label, tone="info"),
        *llm_diagnostic_badges(diagnostics),
        *tool_only_streak_badges(tool_only_streak),
    )
    return make_step_view(
        run=run,
        turn_id=turn_id,
        step_id=f"execution:{step.id}",
        step_type="llm",
        status=execution_step_view_status(step, run=run),
        title="LLM Thinking",
        summary=summary,
        markdown=(
            failure_guidance_markdown(
                message=summary,
                code=step_error.code,
                details=step_error.details,
            )
            if step_error is not None and step.status is ExecutionStepStatus.FAILED
            else None
        ),
        started_at=step.started_at or llm_started_at(run, llm_invocation),
        completed_at=(
            step.completed_at
            or (
                llm_completed_at(run, llm_invocation)
                if step.status
                in {
                    ExecutionStepStatus.COMPLETED,
                    ExecutionStepStatus.FAILED,
                    ExecutionStepStatus.CANCELLED,
                }
                else None
            )
        ),
        badges=badges,
        llm_invocation_id=invocation_id,
        request_render_snapshot_id=request_render_snapshot_id,
        trace_step_id=step.id,
    )
