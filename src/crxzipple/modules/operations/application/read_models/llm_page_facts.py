from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.operations.application.read_models.llm_invocation_filters import (
    LlmOperationsQuery,
    invocation_page_read_limit as _invocation_page_read_limit,
    normalize_query as _normalize_query,
)
from crxzipple.modules.operations.application.read_models.llm_lifecycle_event_sources import (
    recent_llm_events as _recent_llm_events,
    recent_resolver_events as _recent_resolver_events,
)
from crxzipple.modules.operations.application.read_models.llm_overview_sections import (
    llm_health as _health,
)
from crxzipple.modules.operations.application.read_models.llm_page_invocation_sets import (
    collect_llm_page_invocation_sets,
)
from crxzipple.modules.operations.application.read_models.llm_provider_readiness import (
    blocked_profiles as _blocked_profiles,
)
from crxzipple.modules.operations.application.read_models.llm_resolver_sections import (
    resolver_events_by_run_id as _resolver_events_by_run_id,
)
from crxzipple.modules.operations.application.read_models.llm_response_events import (
    events_by_invocation as _events_by_invocation,
    response_event_retention_policy as _response_event_retention_policy,
    response_events_by_invocation as _response_events_by_invocation,
)
from crxzipple.modules.operations.application.read_models.llm_run_contexts import (
    invocation_run_contexts as _invocation_run_contexts,
)
from crxzipple.modules.operations.application.read_models.llm_runtime_metrics import (
    runtime_snapshot as _runtime_snapshot,
)
from crxzipple.modules.operations.application.read_models.ports_llm_agent import (
    OperationsLlmQueryPort,
)
from crxzipple.modules.operations.application.read_models.ports_runtime import (
    OperationsObservationReadPort,
)


@dataclass(frozen=True, slots=True)
class LlmPageFacts:
    now: datetime
    query: LlmOperationsQuery
    profiles: list[Any]
    invocations: list[Any]
    profiles_by_id: dict[str, Any]
    observed_events: list[Any]
    resolver_events: list[Any]
    events_by_invocation: dict[str, list[Any]]
    run_contexts: dict[str, dict[str, str]]
    resolver_events_by_run_id: dict[str, list[Any]]
    runtime_snapshot: Any
    active_invocations: list[Any]
    failed_invocations: list[Any]
    blocked_profiles: list[Any]
    filtered_invocations: list[Any]
    filtered_failed_invocations: list[Any]
    visible_invocations: list[Any]
    streaming_invocations: list[Any]
    health: str
    detail_invocations: tuple[Any, ...]
    response_events_by_invocation: dict[str, list[Any]]
    response_event_retention_policy: str
    owner_call_count: int


def collect_llm_page_facts(
    *,
    llm_service: OperationsLlmQueryPort,
    query: LlmOperationsQuery | None,
    access_service: Any | None,
    run_query: Any | None,
    events_service: Any | None,
    event_definition_registry: Any | None,
    operations_observation: OperationsObservationReadPort | None,
    runtime_metrics: Any | None,
) -> LlmPageFacts:
    now = datetime.now(timezone.utc)
    normalized_query = _normalize_query(query)
    profiles = llm_service.list_profiles()
    invocations = llm_service.list_invocations(
        run_id=(normalized_query.run_id if normalized_query.run_id != "all" else None),
        limit=_invocation_page_read_limit(normalized_query),
    )
    profiles_by_id = {profile.id: profile for profile in profiles}
    observed_events = _recent_llm_events(
        operations_observation=operations_observation,
        events_service=events_service,
        definition_registry=event_definition_registry,
        limit=100,
    )
    resolver_events = _recent_resolver_events(
        operations_observation=operations_observation,
        events_service=events_service,
        definition_registry=event_definition_registry,
        limit=80,
    )
    events_by_invocation = _events_by_invocation(
        (*observed_events, *resolver_events),
    )
    run_contexts = _invocation_run_contexts(run_query, invocations)
    resolver_events_by_run_id = _resolver_events_by_run_id(resolver_events)
    runtime_snapshot = _runtime_snapshot(runtime_metrics)
    blocked_profiles = _blocked_profiles(
        profiles,
        access_service=access_service,
    )
    invocation_sets = collect_llm_page_invocation_sets(
        invocations,
        query=normalized_query,
        profiles_by_id=profiles_by_id,
        observed_events=observed_events,
        now=now,
    )
    health = _health(
        profiles=profiles,
        enabled_profiles=[profile for profile in profiles if profile.enabled],
        active_invocations=invocation_sets.active,
        failed_invocations=invocation_sets.failed,
        blocked_profiles=blocked_profiles,
    )
    response_events_by_invocation = _response_events_by_invocation(
        llm_service,
        invocation_sets.detail,
    )
    response_event_retention_policy = _response_event_retention_policy(llm_service)

    return LlmPageFacts(
        now=now,
        query=normalized_query,
        profiles=profiles,
        invocations=invocations,
        profiles_by_id=profiles_by_id,
        observed_events=observed_events,
        resolver_events=resolver_events,
        events_by_invocation=events_by_invocation,
        run_contexts=run_contexts,
        resolver_events_by_run_id=resolver_events_by_run_id,
        runtime_snapshot=runtime_snapshot,
        active_invocations=invocation_sets.active,
        failed_invocations=invocation_sets.failed,
        blocked_profiles=blocked_profiles,
        filtered_invocations=invocation_sets.filtered,
        filtered_failed_invocations=invocation_sets.filtered_failed,
        visible_invocations=invocation_sets.visible,
        streaming_invocations=invocation_sets.streaming,
        health=health,
        detail_invocations=invocation_sets.detail,
        response_events_by_invocation=response_events_by_invocation,
        response_event_retention_policy=response_event_retention_policy,
        owner_call_count=(
            2
            + len(invocation_sets.detail)
            + (1 if access_service is not None else 0)
            + (1 if run_query is not None else 0)
            + (1 if operations_observation is not None else 0)
            + (1 if events_service is not None else 0)
            + (1 if runtime_metrics is not None else 0)
        ),
    )
