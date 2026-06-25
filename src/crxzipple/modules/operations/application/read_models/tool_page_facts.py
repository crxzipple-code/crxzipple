from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.ports_tooling import (
    OperationsToolQueryPort,
)
from crxzipple.modules.operations.application.read_models.tool_lifecycle_event_sources import (
    recent_tool_events,
)
from crxzipple.modules.operations.application.read_models.tool_metrics import (
    tool_health,
)
from crxzipple.modules.operations.application.read_models.tool_overview_risk import (
    risky_tools as risky_tool_list,
)
from crxzipple.modules.operations.application.read_models.tool_page_run_selection import (
    normalize_tool_query,
)
from crxzipple.modules.operations.application.read_models.tool_page_fact_derivations import (
    tool_page_owner_call_count,
)
from crxzipple.modules.operations.application.read_models.tool_page_run_facts import (
    collect_tool_page_run_facts,
)
from crxzipple.modules.operations.application.read_models.tool_page_source_facts import (
    collect_tool_page_source_facts,
)
from crxzipple.modules.operations.application.read_models.tool_run_query import (
    ToolOperationsQuery,
)
from crxzipple.modules.tool.domain import (
    Tool,
    ToolRun,
    ToolRunAssignment,
    ToolWorkerRegistration,
)

OPERATIONS_TOOL_RUN_QUERY_LIMIT = 500
LONG_RUNNING_SECONDS = 300


@dataclass(frozen=True, slots=True)
class ToolPageFacts:
    now: datetime
    query: ToolOperationsQuery
    tools: list[Tool]
    runs: list[ToolRun]
    workers: list[ToolWorkerRegistration]
    assignments: list[ToolRunAssignment]
    sources: tuple[Any, ...]
    functions: tuple[Any, ...]
    provider_backends: tuple[Any, ...]
    provider_backend_readiness: dict[str, Any]
    discovery_runs_by_source: dict[str, tuple[Any, ...]]
    assignment_by_run: dict[str, ToolRunAssignment]
    active_runs: list[ToolRun]
    running_runs: list[ToolRun]
    waiting_runs: list[ToolRun]
    failed_runs: list[ToolRun]
    long_running_detail_runs: list[ToolRun]
    artifact_count: int
    observed_events: list[Any]
    risky_tools: list[Tool]
    provider_history: OperationsTableSectionModel
    filtered_tool_runs: list[ToolRun]
    visible_tool_runs: list[ToolRun]
    detail_runs: list[ToolRun]
    run_contexts: dict[str, dict[str, str]]
    health: str
    owner_call_count: int


def collect_tool_page_facts(
    *,
    tool_service: OperationsToolQueryPort,
    query: ToolOperationsQuery | None,
    artifact_service: Any | None,
    run_query: Any | None,
    events_service: Any | None,
    event_definition_registry: Any | None,
    operations_observation: Any | None,
) -> ToolPageFacts:
    now = datetime.now(timezone.utc)
    normalized_query = normalize_tool_query(query)
    tools = tool_service.list_tools()
    runs = tool_service.list_tool_runs(limit=OPERATIONS_TOOL_RUN_QUERY_LIMIT)
    workers = tool_service.list_tool_workers()
    assignments = tool_service.list_tool_run_assignments()
    source_facts = collect_tool_page_source_facts(tool_service)
    run_facts = collect_tool_page_run_facts(
        tools=tools,
        runs=runs,
        assignments=assignments,
        query=normalized_query,
        artifact_service=artifact_service,
        run_query=run_query,
        now=now,
        long_running_seconds=LONG_RUNNING_SECONDS,
    )
    observed_events = recent_tool_events(
        operations_observation=operations_observation,
        events_service=events_service,
        definition_registry=event_definition_registry,
        limit=80,
    )
    risky_tools = risky_tool_list(tools)
    health = tool_health(
        tools=tools,
        active_runs=run_facts.active_runs,
        failed_runs=run_facts.failed_runs,
    )
    return ToolPageFacts(
        now=now,
        query=normalized_query,
        tools=tools,
        runs=runs,
        workers=workers,
        assignments=assignments,
        sources=source_facts.sources,
        functions=source_facts.functions,
        provider_backends=source_facts.provider_backends,
        provider_backend_readiness=source_facts.provider_backend_readiness,
        discovery_runs_by_source=source_facts.discovery_runs_by_source,
        assignment_by_run=run_facts.assignment_by_run,
        active_runs=run_facts.active_runs,
        running_runs=run_facts.running_runs,
        waiting_runs=run_facts.waiting_runs,
        failed_runs=run_facts.failed_runs,
        long_running_detail_runs=run_facts.long_running_detail_runs,
        artifact_count=run_facts.artifact_count,
        observed_events=observed_events,
        risky_tools=risky_tools,
        provider_history=run_facts.provider_history,
        filtered_tool_runs=run_facts.filtered_tool_runs,
        visible_tool_runs=run_facts.visible_tool_runs,
        detail_runs=run_facts.detail_runs,
        run_contexts=run_facts.run_contexts,
        health=health,
        owner_call_count=tool_page_owner_call_count(
            provider_backends=source_facts.provider_backends,
            sources=source_facts.sources,
            run_query=run_query,
            operations_observation=operations_observation,
            events_service=events_service,
        ),
    )
