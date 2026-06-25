from __future__ import annotations

from typing import Any

from crxzipple.modules.workbench.application import view_models as models
from crxzipple.modules.orchestration.application.ports import OrchestrationRunQueryPort
from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationRunStage,
    OrchestrationRunStatus,
)
from crxzipple.modules.workbench.application.projection_helpers import optional_text
from crxzipple.modules.workbench.application.run_llm_projection import (
    llm_id,
    llm_step_status,
    llm_summary,
)
from crxzipple.modules.workbench.application.run_text_projection import (
    instruction_summary,
)
from crxzipple.modules.workbench.application.runtime_ref_projection import (
    llm_invocation_for_run,
)
from crxzipple.modules.workbench.application.step_direct_terminal_views import (
    append_access_and_approval_steps,
    append_terminal_step,
)
from crxzipple.modules.workbench.application.step_direct_tool_views import (
    append_completed_tool_steps,
    append_pending_tool_step,
)
from crxzipple.modules.workbench.application.step_view_factory import make_step_view
from crxzipple.modules.workbench.application.execution_projection import (
    llm_completed_at,
    llm_invocation_llm_id,
    llm_started_at,
)


def direct_step_views_for_run(
    run_query: OrchestrationRunQueryPort,
    llm_query: Any | None,
    artifact_query: Any | None,
    run: OrchestrationRun,
    *,
    turn_id: str,
    display_tool_runs: tuple[Any, ...],
) -> tuple[Any, ...]:
    direct_tool_runs = tuple(
        display_tool_run.tool_run
        for display_tool_run in display_tool_runs
        if display_tool_run.source_run.id == run.id
    )
    pending_tool_run_ids = set(run.pending_tool_run_ids)
    llm_invocation = llm_invocation_for_run(
        run_query,
        llm_query,
        run,
    )
    steps: list[Any] = [
        make_step_view(
            run=run,
            turn_id=turn_id,
            step_id="user_input",
            step_type="user_input",
            status="success",
            title="User Input",
            summary=instruction_summary(run),
            started_at=run.created_at,
            completed_at=run.created_at,
        ),
    ]

    _append_queued_step(steps, run=run, turn_id=turn_id)
    _append_llm_step(steps, run=run, turn_id=turn_id, llm_invocation=llm_invocation)
    append_pending_tool_step(
        steps,
        run=run,
        turn_id=turn_id,
        direct_tool_runs=direct_tool_runs,
    )
    append_completed_tool_steps(
        steps,
        run=run,
        turn_id=turn_id,
        display_tool_runs=display_tool_runs,
        pending_tool_run_ids=pending_tool_run_ids,
        artifact_query=artifact_query,
    )
    append_access_and_approval_steps(steps, run=run, turn_id=turn_id)
    append_terminal_step(steps, run=run, turn_id=turn_id)
    return tuple(steps)


def _append_queued_step(
    steps: list[Any],
    *,
    run: OrchestrationRun,
    turn_id: str,
) -> None:
    if run.status is not OrchestrationRunStatus.QUEUED:
        return
    steps.append(
        make_step_view(
            run=run,
            turn_id=turn_id,
            step_id="queued",
            step_type="agent_thinking",
            status="queued",
            title="Queued",
            summary=run.waiting_reason or "Run is waiting for scheduler admission.",
            started_at=run.queued_at or run.created_at,
            completed_at=None,
        ),
    )


def _append_llm_step(
    steps: list[Any],
    *,
    run: OrchestrationRun,
    turn_id: str,
    llm_invocation: object | None,
) -> None:
    if run.started_at is None and run.current_step <= 0:
        return
    steps.append(
        make_step_view(
            run=run,
            turn_id=turn_id,
            step_id=f"llm_{max(run.current_step, 1)}",
            step_type="llm",
            status=llm_step_status(run),
            title="LLM Thinking",
            summary=llm_summary(run, llm_invocation=llm_invocation),
            started_at=llm_started_at(run, llm_invocation),
            completed_at=(
                llm_completed_at(run, llm_invocation)
                if run.stage
                not in {
                    OrchestrationRunStage.LLM,
                    OrchestrationRunStage.RUNNING,
                }
                else None
            ),
            badges=(
                models.StatusBadgeModel(
                    label=(
                        llm_invocation_llm_id(llm_invocation)
                        or llm_id(run)
                        or "Auto"
                    ),
                    tone="info",
                ),
            ),
            llm_invocation_id=optional_text(
                getattr(llm_invocation, "id", None),
            ),
        ),
    )
