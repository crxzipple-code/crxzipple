from __future__ import annotations

from crxzipple.modules.workbench.application import view_models as models
from typing import Any

from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.orchestration.domain.value_objects import (
    ExecutionStepItemKind,
    ExecutionStepItemStatus,
)
from crxzipple.modules.tool.domain import ToolRun
from crxzipple.modules.workbench.application.execution_projection import (
    execution_item_owner_id,
    execution_item_summary,
    execution_item_view_status,
    execution_tool_item_summary,
    summary_text,
)
from crxzipple.modules.workbench.application.step_support_views import (
    generic_execution_step_view,
)
from crxzipple.modules.workbench.application.step_view_factory import make_step_view
from crxzipple.modules.workbench.application.tool_artifact_projection import (
    FAILED_TOOL_RUN_STATUSES,
    TERMINAL_TOOL_RUN_STATUSES,
    tool_artifacts,
    tool_status,
    tool_step_summary,
)


def chain_tool_step_views(
    run: OrchestrationRun,
    *,
    turn_id: str,
    bundle: Any,
    tool_runs_by_id: dict[str, ToolRun],
    artifact_query: Any | None,
) -> tuple[Any, ...]:
    views: list[Any] = []
    for item in bundle.items:
        if item.kind is not ExecutionStepItemKind.TOOL_RUN:
            continue
        tool_run_id = execution_item_owner_id(item, owner_kind="tool_run")
        if tool_run_id is None:
            continue
        tool_run = tool_runs_by_id.get(tool_run_id)
        summary = execution_item_summary(item)
        status = (
            tool_status(tool_run)
            if tool_run is not None
            else execution_item_view_status(item)
        )
        failed = (
            tool_run.status in FAILED_TOOL_RUN_STATUSES
            if tool_run is not None
            else item.status is ExecutionStepItemStatus.FAILED
        )
        artifacts = (
            tool_artifacts(tool_run, artifact_query=artifact_query)
            if tool_run is not None
            and tool_run.status in TERMINAL_TOOL_RUN_STATUSES
            else ()
        )
        tool_label = (
            tool_run.tool_id
            if tool_run is not None
            else summary_text(summary, "tool_id")
            or summary_text(summary, "tool_name")
            or "Tool Call"
        )
        views.append(
            make_step_view(
                run=run,
                turn_id=turn_id,
                step_id=f"execution:{bundle.step.id}:{item.id}",
                step_type="error" if failed else "tool_call",
                status=status,
                title="Tool Failed" if failed else "Tool Call",
                summary=(
                    tool_step_summary(tool_run)
                    if tool_run is not None
                    else execution_tool_item_summary(summary, item)
                ),
                started_at=(
                    tool_run.created_at
                    if tool_run is not None
                    else bundle.step.started_at or item.created_at
                ),
                completed_at=(
                    tool_run.completed_at
                    if tool_run is not None
                    else item.completed_at
                ),
                artifacts=artifacts,
                badges=(
                    models.StatusBadgeModel(
                        label=tool_label,
                        tone="danger" if failed else "info",
                    ),
                ),
                tool_run_id=tool_run_id,
                artifact_id=artifacts[0].artifact_id if artifacts else None,
                trace_step_id=bundle.step.id,
            ),
        )
    if views:
        return tuple(views)
    return (
        generic_execution_step_view(
            run,
            turn_id=turn_id,
            bundle=bundle,
        ),
    )
