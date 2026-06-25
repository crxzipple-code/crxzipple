from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from crxzipple.modules.operations.application.read_models.tool_provider_identity import (
    tool_provider_key,
)
from crxzipple.modules.operations.application.read_models.tool_run_artifact_refs import (
    tool_run_artifact_refs,
)
from crxzipple.modules.operations.application.read_models.tool_run_result_payloads import (
    tool_run_result_summary,
)
from crxzipple.modules.operations.application.read_models.tool_run_browser_details import (
    browser_run_label,
)
from crxzipple.modules.operations.application.read_models.tool_run_execution_labels import (
    assignment_id,
    assignment_status_label,
    lease_expires_label,
    lease_state_label,
    run_duration_label,
    run_progress_label,
)
from crxzipple.modules.operations.application.read_models.tool_run_source_labels import (
    context_value,
    tool_run_orchestration_run_id,
    tool_run_source_label,
    tool_run_source_route,
    tool_run_trace_id,
    tool_run_trace_route,
)
from crxzipple.modules.operations.application.read_models.tool_run_table_labels import (
    tool_label,
    tool_run_filter_search_text,
)
from crxzipple.modules.tool.domain import Tool, ToolRun, ToolRunAssignment


@dataclass(frozen=True, slots=True)
class ToolRunTableFacts:
    tool_label: str
    provider: str
    source: str
    orchestration_run_id: str
    chain_id: str
    step_id: str
    browser: str
    assignment_status: str
    assignment_id: str
    lease_state: str
    lease_expires_at: str
    duration: str
    progress: str
    result: str
    has_artifact: bool
    route: str
    trace: str
    trace_route: str
    search_text: str


def tool_run_table_facts_by_run_id(
    runs: list[ToolRun],
    *,
    tools_by_id: dict[str, Tool],
    assignment_by_run: dict[str, ToolRunAssignment],
    artifact_service: Any | None = None,
    run_contexts: dict[str, dict[str, str]],
    now: datetime,
) -> dict[str, ToolRunTableFacts]:
    return {
        run.id: tool_run_table_facts(
            run,
            tools_by_id=tools_by_id,
            assignment=assignment_by_run.get(run.id),
            artifact_service=artifact_service,
            run_context=run_contexts.get(run.id),
            now=now,
        )
        for run in runs
    }


def tool_run_table_facts(
    run: ToolRun,
    *,
    tools_by_id: dict[str, Tool],
    assignment: ToolRunAssignment | None,
    artifact_service: Any | None,
    run_context: Mapping[str, str] | None,
    now: datetime,
) -> ToolRunTableFacts:
    tool = tools_by_id.get(run.tool_id)
    artifact_count = len(
        tool_run_artifact_refs(run, artifact_service=artifact_service),
    )
    return ToolRunTableFacts(
        tool_label=tool_label(run, tools_by_id),
        provider=tool_provider_key(tool).lower(),
        source=tool_run_source_label(run, run_context=run_context),
        orchestration_run_id=tool_run_orchestration_run_id(
            run,
            run_context=run_context,
        )
        or "-",
        chain_id=context_value(run_context, "chain_id"),
        step_id=context_value(run_context, "step_id"),
        browser=browser_run_label(run),
        assignment_status=assignment_status_label(assignment),
        assignment_id=assignment_id(assignment),
        lease_state=lease_state_label(run, assignment=assignment, now=now),
        lease_expires_at=lease_expires_label(run, assignment=assignment),
        duration=run_duration_label(
            run,
            assignment=assignment,
            now=now,
        ),
        progress=run_progress_label(
            run,
            tool=tools_by_id.get(run.tool_id),
            assignment=assignment,
            now=now,
        ),
        result=tool_run_result_summary(run),
        has_artifact=artifact_count > 0,
        route=tool_run_source_route(run, run_context=run_context),
        trace=tool_run_trace_id(run, run_context=run_context),
        trace_route=tool_run_trace_route(run, run_context=run_context),
        search_text=tool_run_filter_search_text(
            run,
            tool=tool,
            run_context=run_context,
        ),
    )
