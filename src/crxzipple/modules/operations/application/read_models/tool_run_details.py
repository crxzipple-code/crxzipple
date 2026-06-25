from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
    OperationsKeyValueSectionModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.presenters import (
    display_value,
)
from crxzipple.modules.operations.application.read_models.tool_run_assignment_details import (
    assignment_history_section,
)
from crxzipple.modules.operations.application.read_models.tool_lifecycle_event_rows import (
    tool_run_events_section,
)
from crxzipple.modules.operations.application.read_models.tool_provider_identity import (
    provider_history_label,
    tool_provider_key,
)
from crxzipple.modules.operations.application.read_models.tool_run_artifacts import (
    ToolArtifactRunContext,
    tool_run_artifacts_section,
)
from crxzipple.modules.operations.application.read_models.tool_run_result_payloads import (
    tool_run_result_summary,
)
from crxzipple.modules.operations.application.read_models.tool_run_detail_summary import (
    tool_run_detail_summary,
)
from crxzipple.modules.operations.application.read_models.tool_run_detail_projection import (
    latest_assignment_by_run,
    tool_label,
    tool_lookup,
    tool_run_tone,
    trace_id,
    trace_route,
)
from crxzipple.modules.operations.application.read_models.tool_run_error_diagnostics import (
    tool_run_error_facts,
)
from crxzipple.modules.operations.application.read_models.tool_run_detail_payloads import (
    invocation_context_items,
    json_safe_payload,
)
from crxzipple.modules.operations.application.read_models.tool_run_time import (
    tool_run_time,
)
from crxzipple.modules.tool.domain import (
    Tool,
    ToolRun,
    ToolRunAssignment,
)


@dataclass(frozen=True, slots=True)
class ToolRunDetailModel:
    run_id: str
    title: str
    status: str
    tone: str
    summary: tuple[OperationsKeyValueItemModel, ...]
    invocation_context: tuple[OperationsKeyValueItemModel, ...]
    input_payload: Any
    result_payload: Any
    result_summary: str
    error: str
    error_facts: OperationsKeyValueSectionModel
    assignments: OperationsTableSectionModel
    events: OperationsTableSectionModel
    artifacts: OperationsTableSectionModel


def tool_run_details(
    runs: list[ToolRun],
    *,
    tools: list[Tool],
    assignments: list[ToolRunAssignment],
    observed_events: tuple[OperationsObservedEvent, ...],
    artifact_service: Any | None,
    run_contexts: dict[str, dict[str, str]],
    now: datetime,
) -> tuple[ToolRunDetailModel, ...]:
    tools_by_id = tool_lookup(tools)
    assignments_by_run: dict[str, list[ToolRunAssignment]] = {}
    for assignment in assignments:
        assignments_by_run.setdefault(assignment.run_id, []).append(assignment)
    events_by_run: dict[str, list[OperationsObservedEvent]] = {}
    for event in observed_events:
        if event.run_id:
            events_by_run.setdefault(event.run_id, []).append(event)

    return tuple(
        _tool_run_detail(
            run,
            tools_by_id=tools_by_id,
            assignments=assignments_by_run.get(run.id, []),
            events=events_by_run.get(run.id, []),
            artifact_service=artifact_service,
            run_context=run_contexts.get(run.id),
            now=now,
        )
        for run in sorted(runs, key=tool_run_time, reverse=True)[:50]
    )


def _tool_run_detail(
    run: ToolRun,
    *,
    tools_by_id: dict[str, Tool],
    assignments: list[ToolRunAssignment],
    events: list[OperationsObservedEvent],
    artifact_service: Any | None,
    run_context: Mapping[str, str] | None,
    now: datetime,
) -> ToolRunDetailModel:
    assignment = latest_assignment_by_run(assignments).get(run.id)
    return ToolRunDetailModel(
        run_id=run.id,
        title=tool_label(run, tools_by_id),
        status=run.status.value,
        tone=tool_run_tone(run.status),
        summary=tool_run_detail_summary(
            run,
            tools_by_id=tools_by_id,
            assignment=assignment,
            run_context=run_context,
            now=now,
        ),
        invocation_context=invocation_context_items(run),
        input_payload=json_safe_payload(run.input_payload),
        result_payload=json_safe_payload(run.result_payload),
        result_summary=tool_run_result_summary(run),
        error=display_value(run.error_message),
        error_facts=tool_run_error_facts(
            run,
            provider_label=provider_history_label(
                tool_provider_key(tools_by_id.get(run.tool_id)),
            ),
        ),
        assignments=assignment_history_section(assignments),
        events=tool_run_events_section(events, tools_by_id=tools_by_id, run=run),
        artifacts=tool_run_artifacts_section(
            run,
            context=ToolArtifactRunContext(
                tool_label=tool_label(run, tools_by_id),
                trace=trace_id(run, run_context=run_context),
                trace_route=trace_route(run, run_context=run_context),
            ),
            artifact_service=artifact_service,
        ),
    )
