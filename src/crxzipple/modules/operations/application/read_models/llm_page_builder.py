from __future__ import annotations

from time import perf_counter
from typing import Any

from crxzipple.modules.operations.application.read_models.llm_invocation_filters import (
    LlmOperationsQuery,
)
from crxzipple.modules.operations.application.read_models.llm_models import (
    LlmOperationsPage,
)
from crxzipple.modules.operations.application.read_models.llm_overview_actions import (
    llm_actions as _actions,
)
from crxzipple.modules.operations.application.read_models.llm_overview_sections import (
    page_metric_cards as _page_metric_cards,
)
from crxzipple.modules.operations.application.read_models.llm_page_facts import (
    collect_llm_page_facts,
)
from crxzipple.modules.operations.application.read_models.llm_page_sections import (
    llm_page_sections,
)
from crxzipple.modules.operations.application.read_models.llm_page_tabs import (
    llm_page_tabs,
)
from crxzipple.modules.operations.application.read_models.llm_projection_diagnostics import (
    llm_projection_diagnostics,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsModuleRoleModel,
)
from crxzipple.modules.operations.application.read_models.ports_llm_agent import (
    OperationsLlmQueryPort,
)
from crxzipple.modules.operations.application.read_models.ports_runtime import (
    OperationsObservationReadPort,
)
from crxzipple.shared.time import format_datetime_utc


def llm_operations_page(
    *,
    llm_service: OperationsLlmQueryPort,
    query: LlmOperationsQuery | None = None,
    access_service: Any | None = None,
    run_query: Any | None = None,
    events_service: Any | None = None,
    event_definition_registry: Any | None = None,
    operations_observation: OperationsObservationReadPort | None = None,
    runtime_metrics: Any | None = None,
) -> LlmOperationsPage:
    projection_started_at = perf_counter()
    facts = collect_llm_page_facts(
        llm_service=llm_service,
        query=query,
        access_service=access_service,
        run_query=run_query,
        events_service=events_service,
        event_definition_registry=event_definition_registry,
        operations_observation=operations_observation,
        runtime_metrics=runtime_metrics,
    )

    return LlmOperationsPage(
        module="llm",
        title="LLM Runtime",
        subtitle="模型调用、流式输出、限流等待、访问阻塞、Token 与错误的运维视图。",
        health=facts.health,
        updated_at=format_datetime_utc(facts.now),
        auto_refresh=True,
        role=OperationsModuleRoleModel(
            label="Admin",
            can_operate=True,
            scope="llm",
        ),
        metrics=_page_metric_cards(
            profiles=facts.profiles,
            invocations=facts.invocations,
            streaming_invocations=facts.streaming_invocations,
            failed_invocations=facts.failed_invocations,
            health=facts.health,
        ),
        tabs=llm_page_tabs(
            invocations=facts.invocations,
            streaming_invocations=facts.streaming_invocations,
            failed_invocations=facts.failed_invocations,
            profiles=facts.profiles,
            runtime_snapshot=facts.runtime_snapshot,
            observed_events=facts.observed_events,
        ),
        active_tab="invocations",
        actions=_actions(),
        **llm_page_sections(facts=facts, access_service=access_service),
        projection_diagnostics=llm_projection_diagnostics(
            profiles=facts.profiles,
            invocations=facts.invocations,
            observed_events=facts.observed_events,
            resolver_events=facts.resolver_events,
            response_events_by_invocation=facts.response_events_by_invocation,
            owner_call_count=facts.owner_call_count,
            elapsed_ms=(perf_counter() - projection_started_at) * 1000,
            freshness_at=format_datetime_utc(facts.now),
        ),
    )
