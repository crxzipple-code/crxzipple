from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.tool_run_artifacts import (
    ToolArtifactRunContext,
    recent_artifacts_section,
)
from crxzipple.modules.operations.application.read_models.tool_run_artifact_refs import (
    tool_run_artifact_refs,
)
from crxzipple.modules.operations.application.read_models.tool_run_table_facts import (
    tool_run_table_facts_by_run_id,
)
from crxzipple.modules.operations.application.read_models.tool_run_source_labels import (
    tool_run_trace_id,
    tool_run_trace_route,
)
from crxzipple.modules.operations.application.read_models.tool_run_table_labels import (
    tool_label,
)
from crxzipple.modules.operations.application.read_models.tool_run_tables import (
    active_tool_runs_section,
    tool_runs_section,
)
from crxzipple.modules.tool.domain import (
    Tool,
    ToolRun,
    ToolRunAssignment,
)


def tool_runs_table_section(
    runs: list[ToolRun],
    *,
    tools: list[Tool],
    assignment_by_run: dict[str, ToolRunAssignment],
    artifact_service: Any | None,
    run_contexts: dict[str, dict[str, str]],
    now: datetime,
    total_count: int | None = None,
    empty_state: str = "No tool runs recorded.",
) -> OperationsTableSectionModel:
    tools_by_id = tool_lookup(tools)
    return tool_runs_section(
        runs,
        facts_by_run_id=tool_run_table_facts_by_run_id(
            runs,
            tools_by_id=tools_by_id,
            assignment_by_run=assignment_by_run,
            artifact_service=artifact_service,
            run_contexts=run_contexts,
            now=now,
        ),
        total_count=total_count,
        empty_state=empty_state,
    )


def active_tool_runs_table_section(
    runs: list[ToolRun],
    *,
    tools: list[Tool],
    assignment_by_run: dict[str, ToolRunAssignment],
    run_contexts: dict[str, dict[str, str]],
    now: datetime,
) -> OperationsTableSectionModel:
    tools_by_id = tool_lookup(tools)
    return active_tool_runs_section(
        runs,
        facts_by_run_id=tool_run_table_facts_by_run_id(
            runs,
            tools_by_id=tools_by_id,
            assignment_by_run=assignment_by_run,
            artifact_service=None,
            run_contexts=run_contexts,
            now=now,
        ),
    )


def recent_tool_artifacts_section(
    runs: list[ToolRun],
    *,
    tools: list[Tool],
    artifact_service: Any | None,
) -> OperationsTableSectionModel:
    tools_by_id = tool_lookup(tools)
    return recent_artifacts_section(
        runs,
        run_contexts={
            run.id: ToolArtifactRunContext(
                tool_label=tool_label(run, tools_by_id),
                trace=tool_run_trace_id(run),
                trace_route=tool_run_trace_route(run),
            )
            for run in runs
        },
        artifact_service=artifact_service,
    )


def latest_assignment_by_run(
    assignments: list[ToolRunAssignment],
) -> dict[str, ToolRunAssignment]:
    latest: dict[str, ToolRunAssignment] = {}
    for assignment in sorted(
        assignments,
        key=lambda item: item.assigned_at,
        reverse=True,
    ):
        latest.setdefault(assignment.run_id, assignment)
    return latest


def artifact_refs(
    run: ToolRun,
    *,
    artifact_service: Any | None,
) -> list[dict[str, str]]:
    return tool_run_artifact_refs(run, artifact_service=artifact_service)


def tool_lookup(tools: list[Tool]) -> dict[str, Tool]:
    return {tool.id: tool for tool in tools}
