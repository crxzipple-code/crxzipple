from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.operations.application.read_models.tool_provider_identity import (
    tool_provider_key,
)
from crxzipple.modules.operations.application.read_models.tool_page_helpers import (
    artifact_refs,
    tool_lookup,
)
from crxzipple.modules.operations.application.read_models.tool_run_filters import (
    dedupe_tool_runs,
    filter_tool_runs,
)
from crxzipple.modules.operations.application.read_models.tool_run_query import (
    ToolOperationsQuery,
    normalize_tool_operations_query,
    paginate_tool_runs,
    tool_runs_empty_state,
)
from crxzipple.modules.operations.application.read_models.tool_run_table_labels import (
    tool_run_filter_search_text,
)
from crxzipple.modules.tool.domain import Tool, ToolRun, ToolRunAssignment


def normalize_tool_query(query: ToolOperationsQuery | None) -> ToolOperationsQuery:
    return normalize_tool_operations_query(query)


def filter_tool_page_runs(
    runs: list[ToolRun],
    *,
    query: ToolOperationsQuery,
    tools: list[Tool],
    assignment_by_run: dict[str, ToolRunAssignment],
    artifact_service: Any | None,
    now: datetime,
    long_running_seconds: int,
) -> list[ToolRun]:
    tools_by_id = tool_lookup(tools)
    return filter_tool_runs(
        runs,
        query=query,
        assignment_by_run=assignment_by_run,
        provider_key_by_tool_id={tool.id: tool_provider_key(tool) for tool in tools},
        artifact_run_ids={
            run.id
            for run in runs
            if artifact_refs(run, artifact_service=artifact_service)
        },
        search_text_by_run_id={
            run.id: tool_run_filter_search_text(
                run,
                tool=tools_by_id.get(run.tool_id),
            )
            for run in runs
        },
        now=now,
        long_running_seconds=long_running_seconds,
    )


def paginate_tool_page_runs(
    runs: list[ToolRun],
    *,
    query: ToolOperationsQuery,
) -> list[ToolRun]:
    return paginate_tool_runs(runs, query=query)


def dedupe_tool_page_runs(runs: tuple[ToolRun, ...]) -> list[ToolRun]:
    return dedupe_tool_runs(runs)


def tool_page_runs_empty_state(query: ToolOperationsQuery) -> str:
    return tool_runs_empty_state(query)
