from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.tool_page_helpers import (
    artifact_refs,
    latest_assignment_by_run,
)
from crxzipple.modules.operations.application.read_models.tool_page_fact_derivations import (
    tool_page_detail_runs,
    tool_page_run_buckets,
)
from crxzipple.modules.operations.application.read_models.tool_page_run_selection import (
    filter_tool_page_runs,
    paginate_tool_page_runs,
)
from crxzipple.modules.operations.application.read_models.tool_provider_sections import (
    provider_history_section,
)
from crxzipple.modules.operations.application.read_models.tool_run_contexts import (
    tool_run_contexts,
)
from crxzipple.modules.operations.application.read_models.tool_run_query import (
    ToolOperationsQuery,
)
from crxzipple.modules.tool.domain import (
    Tool,
    ToolRun,
    ToolRunAssignment,
)


@dataclass(frozen=True, slots=True)
class ToolPageRunFacts:
    assignment_by_run: dict[str, ToolRunAssignment]
    active_runs: list[ToolRun]
    running_runs: list[ToolRun]
    waiting_runs: list[ToolRun]
    failed_runs: list[ToolRun]
    long_running_detail_runs: list[ToolRun]
    artifact_count: int
    provider_history: OperationsTableSectionModel
    filtered_tool_runs: list[ToolRun]
    visible_tool_runs: list[ToolRun]
    detail_runs: list[ToolRun]
    run_contexts: dict[str, dict[str, str]]


def collect_tool_page_run_facts(
    *,
    tools: list[Tool],
    runs: list[ToolRun],
    assignments: list[ToolRunAssignment],
    query: ToolOperationsQuery,
    artifact_service: Any | None,
    run_query: Any | None,
    now: datetime,
    long_running_seconds: int,
) -> ToolPageRunFacts:
    assignment_by_run = latest_assignment_by_run(assignments)
    run_buckets = tool_page_run_buckets(
        runs,
        assignment_by_run=assignment_by_run,
        now=now,
        long_running_seconds=long_running_seconds,
    )
    filtered_tool_runs = filter_tool_page_runs(
        runs,
        query=query,
        tools=tools,
        assignment_by_run=assignment_by_run,
        artifact_service=artifact_service,
        now=now,
        long_running_seconds=long_running_seconds,
    )
    visible_tool_runs = paginate_tool_page_runs(filtered_tool_runs, query=query)
    detail_runs = tool_page_detail_runs(visible_tool_runs, run_buckets)
    return ToolPageRunFacts(
        assignment_by_run=assignment_by_run,
        active_runs=run_buckets.active,
        running_runs=run_buckets.running,
        waiting_runs=run_buckets.waiting,
        failed_runs=run_buckets.failed,
        long_running_detail_runs=run_buckets.long_running_detail,
        artifact_count=sum(
            1
            for run in runs
            for _ in artifact_refs(run, artifact_service=artifact_service)
        ),
        provider_history=provider_history_section(
            tools=tools,
            runs=runs,
            assignment_by_run=assignment_by_run,
            now=now,
        ),
        filtered_tool_runs=filtered_tool_runs,
        visible_tool_runs=visible_tool_runs,
        detail_runs=detail_runs,
        run_contexts=tool_run_contexts(run_query, detail_runs),
    )
