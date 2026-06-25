from __future__ import annotations

from typing import Mapping

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.tool_run_time import (
    tool_run_time,
)
from crxzipple.modules.operations.application.read_models.tool_run_table_facts import (
    ToolRunTableFacts,
)
from crxzipple.modules.operations.application.read_models.tool_run_table_rows import (
    columns,
    tool_run_row,
)
from crxzipple.modules.tool.domain import ToolRun


def tool_runs_section(
    runs: list[ToolRun],
    *,
    facts_by_run_id: Mapping[str, ToolRunTableFacts],
    total_count: int | None = None,
    empty_state: str = "No tool runs recorded.",
) -> OperationsTableSectionModel:
    rows = tuple(
        tool_run_row(run, facts=facts_by_run_id[run.id])
        for run in sorted(runs, key=tool_run_time, reverse=True)[:50]
    )
    return OperationsTableSectionModel(
        id="tool_runs",
        title="Recent Tool Runs",
        columns=columns(
            ("time", "Time"),
            ("tool", "Tool"),
            ("run_id", "Run ID"),
            ("call_id", "Call ID"),
            ("tool_surface_id", "ToolSurface"),
            ("source", "Source"),
            ("orchestration_run_id", "Turn ID"),
            ("chain_id", "Chain ID"),
            ("step_id", "Step ID"),
            ("browser", "Browser"),
            ("status", "Status"),
            ("assignment_status", "Assignment"),
            ("lease_state", "Lease"),
            ("mode", "Mode"),
            ("strategy", "Strategy"),
            ("environment", "Environment"),
            ("worker", "Worker ID"),
            ("duration", "Duration"),
            ("actions", "Actions"),
        ),
        rows=rows,
        total=total_count if total_count is not None else len(runs),
        view_all_route="/operations/tool?tab=runs",
        empty_state=empty_state,
    )


def active_tool_runs_section(
    runs: list[ToolRun],
    *,
    facts_by_run_id: Mapping[str, ToolRunTableFacts],
) -> OperationsTableSectionModel:
    rows = tuple(
        tool_run_row(run, facts=facts_by_run_id[run.id])
        for run in sorted(runs, key=tool_run_time, reverse=True)[:50]
    )
    return OperationsTableSectionModel(
        id="active_tool_runs",
        title="Active Tool Runs",
        columns=columns(
            ("run_id", "Tool Run ID"),
            ("call_id", "Call ID"),
            ("tool_surface_id", "ToolSurface"),
            ("tool", "Tool"),
            ("source", "Source"),
            ("orchestration_run_id", "Turn ID"),
            ("chain_id", "Chain ID"),
            ("step_id", "Step ID"),
            ("browser", "Browser"),
            ("worker", "Worker ID"),
            ("duration", "Duration"),
            ("progress", "Progress"),
            ("status", "Status"),
            ("actions", "Actions"),
        ),
        rows=rows,
        total=len(runs),
        view_all_route="/operations/tool?tab=runs&status=active",
        empty_state="No active tool runs.",
    )
