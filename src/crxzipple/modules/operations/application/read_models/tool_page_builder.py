from __future__ import annotations

from time import perf_counter
from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsModuleRoleModel,
)
from crxzipple.modules.operations.application.read_models.ports_tooling import (
    OperationsToolQueryPort,
)
from crxzipple.modules.operations.application.read_models.tool_metrics import (
    tool_metric_cards,
)
from crxzipple.modules.operations.application.read_models.tool_models import (
    ToolOperationsPage,
)
from crxzipple.modules.operations.application.read_models.tool_overview_actions import (
    tool_actions,
)
from crxzipple.modules.operations.application.read_models.tool_page_facts import (
    collect_tool_page_facts,
)
from crxzipple.modules.operations.application.read_models.tool_page_sections import (
    tool_page_sections,
)
from crxzipple.modules.operations.application.read_models.tool_page_tabs import (
    tool_page_tabs,
)
from crxzipple.modules.operations.application.read_models.tool_projection_diagnostics import (
    tool_projection_diagnostics,
)
from crxzipple.modules.operations.application.read_models.tool_run_query import ToolOperationsQuery
from crxzipple.shared.time import format_datetime_utc


def tool_operations_page(
    *,
    tool_service: OperationsToolQueryPort,
    query: ToolOperationsQuery | None = None,
    access_service: Any | None = None,
    artifact_service: Any | None = None,
    run_query: Any | None = None,
    events_service: Any | None = None,
    event_definition_registry: Any | None = None,
    operations_observation: Any | None = None,
    runtime_metrics: Any | None = None,
    runtime_registry: Any | None = None,
    runtime_bootstrap_config: Any | None = None,
) -> ToolOperationsPage:
    projection_started_at = perf_counter()
    facts = collect_tool_page_facts(
        tool_service=tool_service,
        query=query,
        artifact_service=artifact_service,
        run_query=run_query,
        events_service=events_service,
        event_definition_registry=event_definition_registry,
        operations_observation=operations_observation,
    )
    sections = tool_page_sections(
        facts=facts,
        tool_service=tool_service,
        access_service=access_service,
        artifact_service=artifact_service,
        runtime_metrics=runtime_metrics,
        runtime_registry=runtime_registry,
    )

    return ToolOperationsPage(
        module="tool",
        title="Tool Runtime",
        subtitle="工具目录、运行队列、worker 占用、权限风险、失败和产物的运维视图。",
        health=facts.health,
        updated_at=format_datetime_utc(facts.now),
        auto_refresh=True,
        role=OperationsModuleRoleModel(
            label="Admin",
            can_operate=True,
            scope="tool",
        ),
        metrics=tool_metric_cards(
            tools=facts.tools,
            runs=facts.runs,
            active_runs=facts.active_runs,
            failed_runs=facts.failed_runs,
            health=facts.health,
            workers=facts.workers,
            runtime_bootstrap_config=runtime_bootstrap_config,
            now=facts.now,
        ),
        tabs=tool_page_tabs(
            run_count=len(facts.runs),
            sources=facts.sources,
            functions=facts.functions,
            worker_count=len(facts.workers),
            waiting_run_count=len(facts.waiting_runs),
            provider_history_count=facts.provider_history.total,
            active_run_count=len(facts.active_runs),
            risky_tool_count=len(facts.risky_tools),
            artifact_count=facts.artifact_count,
            observed_event_count=len(facts.observed_events),
        ),
        active_tab="runs",
        actions=tool_actions(),
        **sections,
        projection_diagnostics=tool_projection_diagnostics(
            tools=facts.tools,
            runs=facts.runs,
            workers=facts.workers,
            assignments=facts.assignments,
            sources=facts.sources,
            functions=facts.functions,
            provider_backends=facts.provider_backends,
            discovery_runs_by_source=facts.discovery_runs_by_source,
            observed_events=facts.observed_events,
            owner_call_count=facts.owner_call_count,
            elapsed_ms=(perf_counter() - projection_started_at) * 1000,
            freshness_at=format_datetime_utc(facts.now),
        ),
    )
