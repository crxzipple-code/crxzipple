from __future__ import annotations

from datetime import datetime
from typing import Mapping

from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
)
from crxzipple.modules.operations.application.read_models.presenters import (
    display_value,
    title_label,
)
from crxzipple.modules.operations.application.read_models.tool_run_detail_projection import (
    assignment_id,
    context_value,
    lease_state_label,
    orchestration_run_id,
    source_label,
    tool_label,
    tool_run_tone,
    trace_id,
)
from crxzipple.modules.operations.application.read_models.tool_metric_values import (
    duration_label,
)
from crxzipple.modules.operations.application.read_models.tool_run_browser_details import (
    browser_profile_summary_items,
)
from crxzipple.modules.operations.application.read_models.tool_run_time import (
    tool_run_duration_seconds,
)
from crxzipple.modules.tool.domain import Tool, ToolRun, ToolRunAssignment


def tool_run_detail_summary(
    run: ToolRun,
    *,
    tools_by_id: dict[str, Tool],
    assignment: ToolRunAssignment | None,
    run_context: Mapping[str, str] | None,
    now: datetime,
) -> tuple[OperationsKeyValueItemModel, ...]:
    return (
        OperationsKeyValueItemModel(label="Tool", value=tool_label(run, tools_by_id)),
        OperationsKeyValueItemModel(
            label="Status",
            value=title_label(run.status.value),
            tone=tool_run_tone(run.status),
        ),
        *browser_profile_summary_items(run),
        OperationsKeyValueItemModel(label="Mode", value=run.target.mode.value),
        OperationsKeyValueItemModel(label="Strategy", value=run.target.strategy.value),
        OperationsKeyValueItemModel(
            label="Environment",
            value=run.target.environment.value,
        ),
        OperationsKeyValueItemModel(
            label="Attempt",
            value=f"{run.attempt_count}/{run.max_attempts}",
        ),
        OperationsKeyValueItemModel(label="Worker ID", value=display_value(run.worker_id)),
        OperationsKeyValueItemModel(
            label="Assignment",
            value=assignment_id(assignment),
        ),
        OperationsKeyValueItemModel(
            label="Lease",
            value=lease_state_label(run, assignment=assignment, now=now),
        ),
        OperationsKeyValueItemModel(
            label="Duration",
            value=duration_label(
                tool_run_duration_seconds(run, assignment=assignment, now=now),
            ),
        ),
        OperationsKeyValueItemModel(
            label="Source",
            value=source_label(run, run_context=run_context),
        ),
        OperationsKeyValueItemModel(
            label="Call ID",
            value=display_value(run.call_id),
        ),
        OperationsKeyValueItemModel(
            label="ToolSurface",
            value=display_value(run.tool_surface_id),
        ),
        OperationsKeyValueItemModel(
            label="Turn ID",
            value=orchestration_run_id(run, run_context=run_context) or "-",
        ),
        OperationsKeyValueItemModel(
            label="Chain ID",
            value=context_value(run_context, "chain_id"),
        ),
        OperationsKeyValueItemModel(
            label="Step ID",
            value=context_value(run_context, "step_id"),
        ),
        OperationsKeyValueItemModel(
            label="Step Kind",
            value=context_value(run_context, "step_kind"),
        ),
        OperationsKeyValueItemModel(
            label="Trace",
            value=trace_id(run, run_context=run_context),
        ),
    )
