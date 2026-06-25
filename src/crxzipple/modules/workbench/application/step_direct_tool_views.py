from __future__ import annotations

from typing import Any

from crxzipple.modules.workbench.application import view_models as models
from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.orchestration.domain.value_objects import OrchestrationRunStatus
from crxzipple.modules.workbench.application.step_view_factory import make_step_view
from crxzipple.modules.workbench.application.tool_artifact_projection import (
    FAILED_TOOL_RUN_STATUSES,
    TERMINAL_TOOL_RUN_STATUSES,
    tool_artifacts,
    tool_badge_tone,
    tool_call_summary,
    tool_status as tool_run_status,
    tool_step_summary,
)


def append_pending_tool_step(
    steps: list[Any],
    *,
    run: OrchestrationRun,
    turn_id: str,
    direct_tool_runs: tuple[Any, ...],
) -> None:
    if not run.pending_tool_run_ids:
        return
    pending_tool_run = direct_tool_runs[0] if direct_tool_runs else None
    steps.append(
        make_step_view(
            run=run,
            turn_id=turn_id,
            step_id="tool_wait",
            step_type="tool_call",
            status=(
                "waiting"
                if run.status is OrchestrationRunStatus.WAITING
                else "running"
            ),
            title="Tool Execution",
            summary=(
                tool_call_summary(pending_tool_run)
                if pending_tool_run is not None
                else run.waiting_reason or "Waiting for pending tool runs to finish."
            ),
            started_at=run.updated_at,
            completed_at=None,
            badges=(
                models.StatusBadgeModel(
                    label=(
                        pending_tool_run.tool_id
                        if pending_tool_run is not None
                        else "Tool Call"
                    ),
                    tone="info",
                ),
            ),
            tool_run_id=run.pending_tool_run_ids[0],
        ),
    )


def append_completed_tool_steps(
    steps: list[Any],
    *,
    run: OrchestrationRun,
    turn_id: str,
    display_tool_runs: tuple[Any, ...],
    pending_tool_run_ids: set[str],
    artifact_query: Any | None,
) -> None:
    for display_tool_run in display_tool_runs:
        source_run = display_tool_run.source_run
        tool_run = display_tool_run.tool_run
        if source_run.id == run.id and tool_run.id in pending_tool_run_ids:
            continue
        tool_status = tool_run_status(tool_run)
        artifacts = (
            tool_artifacts(tool_run, artifact_query=artifact_query)
            if tool_run.status in TERMINAL_TOOL_RUN_STATUSES
            else ()
        )
        steps.append(
            make_step_view(
                run=source_run,
                turn_id=turn_id,
                step_id=f"tool_{tool_run.id}",
                step_type=(
                    "error"
                    if tool_run.status in FAILED_TOOL_RUN_STATUSES
                    else "tool_call"
                ),
                status=tool_status,
                title=(
                    "Tool Failed"
                    if tool_run.status in FAILED_TOOL_RUN_STATUSES
                    else "Tool Call"
                ),
                summary=tool_step_summary(tool_run),
                started_at=tool_run.created_at,
                completed_at=(
                    tool_run.completed_at
                    if tool_run.status in TERMINAL_TOOL_RUN_STATUSES
                    else None
                ),
                artifacts=artifacts,
                badges=(
                    models.StatusBadgeModel(
                        label=tool_run.tool_id,
                        tone=tool_badge_tone(tool_run),
                    ),
                ),
                tool_run_id=tool_run.id,
                artifact_id=artifacts[0].artifact_id if artifacts else None,
            ),
        )
