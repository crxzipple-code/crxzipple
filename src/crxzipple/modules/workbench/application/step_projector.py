from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.orchestration.application.ports import OrchestrationRunQueryPort
from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.orchestration.domain.value_objects import (
    ExecutionStepKind,
    ExecutionStepStatus,
)
from crxzipple.modules.tool.domain import ToolRun
from crxzipple.modules.workbench.application.execution_projection import (
    execution_step_bundles,
    execution_step_view_status,
)
from crxzipple.modules.workbench.application.step_diagnostics import (
    llm_bundle_is_tool_only,
)
from crxzipple.modules.workbench.application.run_identity_projection import (
    turn_id as run_turn_id,
)
from crxzipple.modules.workbench.application.run_text_projection import (
    instruction_summary,
    output_text as run_output_text,
)
from crxzipple.modules.workbench.application.step_detail_projection import (
    missing_access_payload,
)
from crxzipple.modules.workbench.application.step_direct_views import (
    direct_step_views_for_run,
)
from crxzipple.modules.workbench.application.step_llm_views import (
    chain_llm_step_views,
)
from crxzipple.modules.workbench.application.step_view_factory import make_step_view
from crxzipple.modules.workbench.application.step_support_views import (
    chain_approval_step_view,
    generic_execution_step_view,
    missing_access_step_view,
)
from crxzipple.modules.workbench.application.step_tool_views import (
    chain_tool_step_views,
)
from crxzipple.modules.workbench.application.tool_run_projection import (
    display_tool_runs as project_display_tool_runs,
)


@dataclass(frozen=True, slots=True)
class WorkbenchRunStepProjector:
    run_query: OrchestrationRunQueryPort
    tool_query: Any | None = None
    artifact_query: Any | None = None
    llm_query: Any | None = None
    session_query: Any | None = None

    def project_step_views_for_run(
        self,
        run: OrchestrationRun,
        *,
        candidate_runs: list[OrchestrationRun] | None = None,
        tool_runs: list[ToolRun] | None = None,
    ) -> tuple[Any, ...]:
        turn_id = run_turn_id(run)
        display_tool_runs = project_display_tool_runs(
            self.run_query,
            self.tool_query,
            run,
            candidate_runs=candidate_runs,
            tool_runs=tool_runs,
        )
        chain_steps = _chain_step_views_for_run(
            self.run_query,
            self.llm_query,
            self.artifact_query,
            self.session_query,
            run,
            turn_id=turn_id,
            display_tool_runs=display_tool_runs,
        )
        if chain_steps:
            return chain_steps
        return direct_step_views_for_run(
            self.run_query,
            self.llm_query,
            self.artifact_query,
            run,
            turn_id=turn_id,
            display_tool_runs=display_tool_runs,
        )


def _chain_step_views_for_run(
    run_query: OrchestrationRunQueryPort,
    llm_query: Any | None,
    artifact_query: Any | None,
    session_query: Any | None,
    run: OrchestrationRun,
    *,
    turn_id: str,
    display_tool_runs: tuple[Any, ...],
) -> tuple[Any, ...]:
    bundles = execution_step_bundles(run_query, run.id)
    if not bundles:
        return ()
    tool_runs_by_id = {
        display_tool_run.tool_run.id: display_tool_run.tool_run
        for display_tool_run in display_tool_runs
    }
    views: list[Any] = []
    tool_only_streak = 0
    for bundle in bundles:
        step = bundle.step
        if step.kind is ExecutionStepKind.INTAKE:
            views.append(
                make_step_view(
                    run=run,
                    turn_id=turn_id,
                    step_id=f"execution:{step.id}",
                    step_type="user_input",
                    status=(
                        "success"
                        if step.status is ExecutionStepStatus.COMPLETED
                        else execution_step_view_status(step, run=run)
                    ),
                    title="User Input",
                    summary=instruction_summary(run),
                    started_at=run.created_at,
                    completed_at=run.created_at,
                    trace_step_id=step.id,
                ),
            )
            continue
        if step.kind is ExecutionStepKind.LLM:
            tool_only_streak = (
                tool_only_streak + 1
                if llm_bundle_is_tool_only(bundle, llm_query=llm_query)
                else 0
            )
            views.extend(
                chain_llm_step_views(
                    llm_query,
                    session_query,
                    run,
                    turn_id=turn_id,
                    bundle=bundle,
                    tool_only_streak=tool_only_streak,
                ),
            )
            continue
        if step.kind is ExecutionStepKind.TOOL_BATCH:
            views.extend(
                chain_tool_step_views(
                    run,
                    turn_id=turn_id,
                    bundle=bundle,
                    tool_runs_by_id=tool_runs_by_id,
                    artifact_query=artifact_query,
                ),
            )
            continue
        if step.kind is ExecutionStepKind.APPROVAL:
            approval_view = chain_approval_step_view(
                run,
                turn_id=turn_id,
                bundle=bundle,
            )
            if approval_view is not None:
                views.append(approval_view)
            continue
        if step.kind is ExecutionStepKind.FINAL_RESPONSE:
            final_output_text = run_output_text(run)
            views.append(
                make_step_view(
                    run=run,
                    turn_id=turn_id,
                    step_id=f"execution:{step.id}",
                    step_type="final_response",
                    status=execution_step_view_status(step, run=run),
                    title="Final Response",
                    summary=final_output_text or "Run completed.",
                    markdown=final_output_text,
                    started_at=step.started_at or step.created_at,
                    completed_at=step.completed_at or run.completed_at or run.updated_at,
                    trace_step_id=step.id,
                ),
            )
            continue
        views.append(
            generic_execution_step_view(
                run,
                turn_id=turn_id,
                bundle=bundle,
            ),
        )
    access_payload = missing_access_payload(run)
    if access_payload is not None and not any(
        view.type == "missing_access" for view in views
    ):
        views.append(
            missing_access_step_view(
                run,
                turn_id=turn_id,
                access_payload=access_payload,
            ),
        )
    return tuple(views)
