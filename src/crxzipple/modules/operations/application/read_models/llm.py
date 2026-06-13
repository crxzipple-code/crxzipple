from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from typing import Any

from crxzipple.modules.llm.domain import LlmInvocation, LlmInvocationStatus, LlmProfile
from crxzipple.modules.orchestration.domain import ExecutionOwnerReference
from crxzipple.modules.operations.application.observation import (
    OperationsObservedEvent,
    observed_event_from_record,
)
from crxzipple.modules.operations.application.read_models.ports import (
    OperationsLlmQueryPort,
    OperationsObservationReadPort,
)
from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsChartSectionModel,
    OperationsChartSegmentModel,
    OperationsKeyValueItemModel,
    OperationsKeyValueSectionModel,
    OperationsModuleOverview,
    OperationsModuleRoleModel,
    OperationsTabModel,
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
    RuntimeActionModel,
)
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc

_LLM_LIMITER_PREFIX = "llm.profile_limiter."
_LLM_LIMITER_ACTIVE = f"{_LLM_LIMITER_PREFIX}active"
_LLM_LIMITER_WAITERS = f"{_LLM_LIMITER_PREFIX}waiters"
_LLM_LIMITER_WAIT_SECONDS = f"{_LLM_LIMITER_PREFIX}wait_seconds"
_RECENT_WINDOW = timedelta(hours=24)
_LONG_RUNNING_SECONDS = 120
_MAX_LLM_EVENT_TOPICS = 240
_MAX_RECENT_LLM_EVENTS = 320
_RECENT_LLM_TOPIC_LIMIT = 100
_INVOCATION_OVERVIEW_LIMIT = 240
_INVOCATION_PAGE_BASE_LIMIT = 240
_LLM_DIRECT_EVENT_TOPICS = (
    "events.named.llm.profile_registered",
    "events.named.llm.profile_updated",
    "events.named.llm.invocation_started",
    "events.named.llm.invocation_succeeded",
    "events.named.llm.invocation_failed",
    "events.named.llm.stream_delta_observed",
    "events.named.orchestration.run.llm_text_delta",
    "llm.profile_registered",
    "llm.profile_updated",
    "llm.invocation_started",
    "llm.invocation_succeeded",
    "llm.invocation_failed",
    "llm.stream_delta_observed",
    "orchestration.run.llm_text_delta",
)
_LLM_RESOLVER_EVENT_TOPICS = (
    "events.named.orchestration.llm_resolved",
    "orchestration.llm_resolved",
)


@dataclass(frozen=True, slots=True)
class LlmOperationsQuery:
    status: str = "all"
    time_window: str = "all"
    search: str = ""
    llm_id: str = "all"
    provider: str = "all"
    streaming: str = "all"
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True, slots=True)
class LlmInvocationDetailModel:
    invocation_id: str
    title: str
    status: str
    tone: str
    summary: tuple[OperationsKeyValueItemModel, ...]
    request_context: tuple[OperationsKeyValueItemModel, ...]
    request_payload: Any
    result_payload: Any
    result_summary: str
    error: str
    resolver: OperationsKeyValueSectionModel
    error_facts: OperationsKeyValueSectionModel
    policy_trace: OperationsTableSectionModel
    response_items: OperationsTableSectionModel
    response_events: OperationsTableSectionModel
    events: OperationsTableSectionModel


def defer_llm_invocation_details_payload(payload: dict[str, Any]) -> None:
    payload["invocation_details"] = []


def find_llm_invocation_detail_payload(
    payload: dict[str, Any],
    invocation_id: str,
) -> dict[str, Any] | None:
    details = payload.get("invocation_details")
    if not isinstance(details, list):
        return None
    normalized_invocation_id = invocation_id.strip()
    for item in details:
        if (
            isinstance(item, dict)
            and str(item.get("invocation_id") or "") == normalized_invocation_id
        ):
            return item
    return None


@dataclass(frozen=True, slots=True)
class LlmOperationsPage:
    module: str
    title: str
    subtitle: str
    health: str
    updated_at: str
    auto_refresh: bool
    role: OperationsModuleRoleModel
    metrics: tuple[MetricCardModel, ...]
    tabs: tuple[OperationsTabModel, ...]
    active_tab: str
    actions: tuple[RuntimeActionModel, ...]
    provider_access_health: OperationsTableSectionModel
    provider_auth_blocked: OperationsTableSectionModel
    model_resolver: OperationsChartSectionModel
    rate_limiter: OperationsKeyValueSectionModel
    limiter_queue: OperationsTableSectionModel
    streaming_requests: OperationsTableSectionModel
    recent_invocations: OperationsTableSectionModel
    failed_invocations: OperationsTableSectionModel
    latency: OperationsChartSectionModel
    token_usage: OperationsChartSectionModel
    invocation_rate: OperationsChartSectionModel
    stream_health: OperationsKeyValueSectionModel
    execution_blocking_risk: OperationsKeyValueSectionModel
    fallback_problems: OperationsTableSectionModel
    context_pressure: OperationsChartSectionModel
    model_availability: OperationsTableSectionModel
    error_summary: OperationsTableSectionModel
    llm_lifecycle_events: OperationsTableSectionModel
    invocation_details: tuple[LlmInvocationDetailModel, ...]


@dataclass(slots=True)
class LlmOperationsReadModelProvider:
    llm_service: OperationsLlmQueryPort
    access_service: Any | None = None
    run_query: Any | None = None
    events_service: Any | None = None
    event_definition_registry: Any | None = None
    operations_observation: OperationsObservationReadPort | None = None
    runtime_metrics: Any | None = None

    def overview(self) -> OperationsModuleOverview:
        now = datetime.now(timezone.utc)
        profiles = self.llm_service.list_profiles()
        invocations = self.llm_service.list_invocations(
            limit=_INVOCATION_OVERVIEW_LIMIT,
        )
        counts = Counter(invocation.status for invocation in invocations)
        active_invocations = [
            invocation
            for invocation in invocations
            if invocation.status is LlmInvocationStatus.RUNNING
        ]
        failed_invocations = [
            invocation
            for invocation in invocations
            if invocation.status is LlmInvocationStatus.FAILED
        ]
        enabled_profiles = [profile for profile in profiles if profile.enabled]
        token_total = _token_total(invocations)
        health = _health(
            profiles=profiles,
            enabled_profiles=enabled_profiles,
            active_invocations=active_invocations,
            failed_invocations=failed_invocations,
            blocked_profiles=_blocked_profiles(
                profiles,
                access_service=self.access_service,
            ),
        )

        return OperationsModuleOverview(
            module="llm",
            title="LLM",
            subtitle="监控模型配置、调用状态、失败、限流键与上下文容量。",
            health=health,
            updated_at=format_datetime_utc(now),
            metrics=(
                MetricCardModel(
                    id="health",
                    label="Overall Health",
                    value=_health_label(health),
                    delta=_health_delta(health),
                    tone=_health_tone(health),
                ),
                MetricCardModel(
                    id="profiles",
                    label="LLM Profiles",
                    value=str(len(profiles)),
                    delta=f"{len(enabled_profiles)} enabled",
                    tone="success" if enabled_profiles else "warning",
                ),
                MetricCardModel(
                    id="active_invocations",
                    label="Active Invocations",
                    value=str(counts[LlmInvocationStatus.RUNNING]),
                    delta=f"{counts[LlmInvocationStatus.SUCCEEDED]} succeeded",
                    tone="info" if active_invocations else "success",
                ),
                MetricCardModel(
                    id="failed_invocations",
                    label="Failed Invocations",
                    value=str(len(failed_invocations)),
                    delta="retained invocation records",
                    tone="danger" if failed_invocations else "success",
                ),
                MetricCardModel(
                    id="tokens",
                    label="Tokens",
                    value=str(token_total),
                    delta="reported by providers",
                    tone="info" if token_total else "neutral",
                ),
                MetricCardModel(
                    id="context",
                    label="Max Context",
                    value=_max_context_label(profiles),
                    delta="largest configured window",
                    tone="neutral",
                ),
            ),
            queue=_queue_rows(invocations, now=now),
            lane_locks=_profile_limit_rows(profiles),
            executor=_profile_rows(profiles, invocations),
            actions=_actions(),
        )

    def page(
        self,
        query: LlmOperationsQuery | None = None,
    ) -> LlmOperationsPage:
        now = datetime.now(timezone.utc)
        query = _normalize_query(query)
        profiles = self.llm_service.list_profiles()
        invocations = self.llm_service.list_invocations(
            limit=_invocation_page_read_limit(query),
        )
        profiles_by_id = {profile.id: profile for profile in profiles}
        observed_events = _recent_llm_events(
            operations_observation=self.operations_observation,
            events_service=self.events_service,
            definition_registry=self.event_definition_registry,
            limit=100,
        )
        resolver_events = _recent_resolver_events(
            operations_observation=self.operations_observation,
            events_service=self.events_service,
            definition_registry=self.event_definition_registry,
            limit=80,
        )
        events_by_invocation = _events_by_invocation(
            (*observed_events, *resolver_events),
        )
        run_contexts = _invocation_run_contexts(self.run_query, invocations)
        resolver_events_by_run_id = _resolver_events_by_run_id(resolver_events)
        runtime_snapshot = _runtime_snapshot(self.runtime_metrics)
        active_invocations = [
            invocation
            for invocation in invocations
            if invocation.status is LlmInvocationStatus.RUNNING
        ]
        failed_invocations = [
            invocation
            for invocation in invocations
            if invocation.status is LlmInvocationStatus.FAILED
        ]
        blocked_profiles = _blocked_profiles(
            profiles,
            access_service=self.access_service,
        )
        filtered_invocations = _filter_invocations(
            invocations,
            query=query,
            profiles_by_id=profiles_by_id,
            observed_events=observed_events,
            now=now,
        )
        filtered_failed_invocations = [
            invocation
            for invocation in filtered_invocations
            if invocation.status is LlmInvocationStatus.FAILED
        ]
        visible_invocations = _paginate_invocations(filtered_invocations, query=query)
        streaming_invocations = _streaming_invocations(
            invocations,
            profiles_by_id=profiles_by_id,
            observed_events=observed_events,
        )
        health = _health(
            profiles=profiles,
            enabled_profiles=[profile for profile in profiles if profile.enabled],
            active_invocations=active_invocations,
            failed_invocations=failed_invocations,
            blocked_profiles=blocked_profiles,
        )
        detail_invocations = _dedupe_invocations(
            (*visible_invocations, *active_invocations, *failed_invocations[:20]),
        )
        response_events_by_invocation = _response_events_by_invocation(
            self.llm_service,
            detail_invocations,
        )

        return LlmOperationsPage(
            module="llm",
            title="LLM Runtime",
            subtitle="模型调用、流式输出、限流等待、访问阻塞、Token 与错误的运维视图。",
            health=health,
            updated_at=format_datetime_utc(now),
            auto_refresh=True,
            role=OperationsModuleRoleModel(
                label="Admin",
                can_operate=True,
                scope="llm",
            ),
            metrics=_page_metric_cards(
                profiles=profiles,
                invocations=invocations,
                streaming_invocations=streaming_invocations,
                failed_invocations=failed_invocations,
                health=health,
            ),
            tabs=(
                OperationsTabModel(
                    id="invocations",
                    label="Invocations",
                    count=len(invocations),
                ),
                OperationsTabModel(
                    id="streaming",
                    label="Streaming Requests",
                    count=len(streaming_invocations),
                ),
                OperationsTabModel(
                    id="rate_limits",
                    label="Rate Limits",
                    count=_limiter_waiter_count(runtime_snapshot),
                    tone=(
                        "warning"
                        if _limiter_waiter_count(runtime_snapshot) > 0
                        else "neutral"
                    ),
                ),
                OperationsTabModel(
                    id="token_usage",
                    label="Token Usage",
                    count=_token_total(invocations),
                ),
                OperationsTabModel(
                    id="errors",
                    label="Errors",
                    count=len(failed_invocations),
                    tone="danger" if failed_invocations else "neutral",
                ),
                OperationsTabModel(
                    id="models",
                    label="Models",
                    count=len(profiles),
                ),
                OperationsTabModel(
                    id="providers",
                    label="Providers",
                    count=len({profile.provider.value for profile in profiles}),
                ),
                OperationsTabModel(
                    id="events",
                    label="Events",
                    count=len(observed_events),
                ),
            ),
            active_tab="invocations",
            actions=_actions(),
            provider_access_health=_provider_access_health_section(
                profiles,
                invocations=invocations,
                access_service=self.access_service,
            ),
            provider_auth_blocked=_provider_auth_blocked_section(
                profiles,
                invocations=invocations,
                access_service=self.access_service,
            ),
            model_resolver=_model_resolver_section(resolver_events),
            rate_limiter=_rate_limiter_section(
                profiles,
                runtime_snapshot=runtime_snapshot,
            ),
            limiter_queue=_limiter_queue_section(
                profiles,
                runtime_snapshot=runtime_snapshot,
            ),
            streaming_requests=_streaming_requests_section(
                streaming_invocations,
                profiles_by_id=profiles_by_id,
                events_by_invocation=events_by_invocation,
                run_contexts=run_contexts,
                now=now,
            ),
            recent_invocations=_recent_invocations_section(
                visible_invocations,
                profiles_by_id=profiles_by_id,
                observed_events=observed_events,
                events_by_invocation=events_by_invocation,
                run_contexts=run_contexts,
                total_count=len(filtered_invocations),
                empty_state=_invocations_empty_state(query),
            ),
            failed_invocations=_failed_invocations_section(
                filtered_failed_invocations[:50],
                profiles_by_id=profiles_by_id,
                observed_events=observed_events,
                events_by_invocation=events_by_invocation,
                run_contexts=run_contexts,
                total_count=len(filtered_failed_invocations),
                empty_state=_invocations_empty_state(query)
                if _has_invocation_filters(query)
                else "No failed LLM invocations.",
            ),
            latency=_latency_section(invocations, profiles_by_id=profiles_by_id),
            token_usage=_token_usage_section(invocations),
            invocation_rate=_invocation_rate_section(invocations),
            stream_health=_stream_health_section(
                profiles,
                streaming_invocations=streaming_invocations,
                observed_events=observed_events,
                now=now,
            ),
            execution_blocking_risk=_execution_blocking_risk_section(
                profiles,
                active_invocations=active_invocations,
                runtime_snapshot=runtime_snapshot,
                now=now,
            ),
            fallback_problems=_fallback_problems_section(resolver_events),
            context_pressure=_context_pressure_section(
                invocations,
                profiles_by_id=profiles_by_id,
            ),
            model_availability=_model_availability_section(
                profiles,
                access_service=self.access_service,
            ),
            error_summary=_error_summary_section(failed_invocations),
            llm_lifecycle_events=_llm_lifecycle_events_section(observed_events),
            invocation_details=_invocation_details(
                detail_invocations,
                profiles_by_id=profiles_by_id,
                events_by_invocation=events_by_invocation,
                run_contexts=run_contexts,
                resolver_events_by_run_id=resolver_events_by_run_id,
                observed_events=observed_events,
                response_events_by_invocation=response_events_by_invocation,
            ),
        )


def _health(
    *,
    profiles: list[LlmProfile],
    enabled_profiles: list[LlmProfile],
    active_invocations: list[LlmInvocation],
    failed_invocations: list[LlmInvocation],
    blocked_profiles: list[LlmProfile] | None = None,
) -> str:
    if failed_invocations or blocked_profiles:
        return "warning"
    if active_invocations:
        return "healthy"
    if not profiles or not enabled_profiles:
        return "warning"
    return "healthy"


def _health_label(health: str) -> str:
    return {
        "healthy": "Healthy",
        "warning": "Warning",
        "error": "Error",
    }.get(health, "Unknown")


def _health_delta(health: str) -> str:
    return {
        "healthy": "LLM runtime state is queryable",
        "warning": "Operator attention recommended",
        "error": "Operator action required",
    }.get(health, "Insufficient data")


def _health_tone(health: str) -> str:
    return {
        "healthy": "success",
        "warning": "warning",
        "error": "danger",
    }.get(health, "neutral")


def _page_metric_cards(
    *,
    profiles: list[LlmProfile],
    invocations: list[LlmInvocation],
    streaming_invocations: list[LlmInvocation],
    failed_invocations: list[LlmInvocation],
    health: str,
) -> tuple[MetricCardModel, ...]:
    completed_durations = [
        duration
        for invocation in invocations
        for duration in (_duration_seconds(invocation),)
        if duration is not None and invocation.status is LlmInvocationStatus.SUCCEEDED
    ]
    average_latency = (
        sum(completed_durations) / len(completed_durations)
        if completed_durations
        else None
    )
    return (
        MetricCardModel(
            id="health",
            label="Overall Health",
            value=_health_label(health),
            delta=_health_delta(health),
            tone=_health_tone(health),
        ),
        MetricCardModel(
            id="invocations",
            label="Invocations",
            value=str(len(invocations)),
            delta=f"{len([item for item in invocations if item.status is LlmInvocationStatus.RUNNING])} running",
            tone="info" if invocations else "neutral",
        ),
        MetricCardModel(
            id="tokens",
            label="Tokens",
            value=str(_token_total(invocations)),
            delta="reported by providers",
            tone="info" if _token_total(invocations) else "neutral",
        ),
        MetricCardModel(
            id="streaming",
            label="Streaming",
            value=str(len(streaming_invocations)),
            delta="stream-capable or observed stream calls",
            tone="info" if streaming_invocations else "neutral",
        ),
        MetricCardModel(
            id="errors",
            label="Errors",
            value=str(len(failed_invocations)),
            delta="failed retained invocations",
            tone="danger" if failed_invocations else "success",
        ),
        MetricCardModel(
            id="latency",
            label="Avg Latency",
            value=_seconds_label(average_latency),
            delta=f"{len(profiles)} configured profiles",
            tone="neutral",
        ),
    )


def _actions() -> tuple[RuntimeActionModel, ...]:
    return (
        RuntimeActionModel(
            id="open_invocation",
            label="Open Invocation",
            owner="llm",
            kind="navigation",
            method="GET",
            endpoint="/operations/llm/invocations/{invocation_id}/detail",
        ),
        RuntimeActionModel(
            id="open_trace",
            label="Open Trace",
            owner="events",
            kind="navigation",
            method="GET",
            endpoint="/ui/trace/{trace_id}",
        ),
        RuntimeActionModel(
            id="open_access",
            label="Open Access",
            owner="access",
            kind="navigation",
            method="GET",
            endpoint="/operations/access",
        ),
        RuntimeActionModel(
            id="view_limits",
            label="View Limits",
            owner="llm",
            kind="navigation",
            method="GET",
            endpoint="/settings/llm-profiles",
        ),
        RuntimeActionModel(
            id="configure_pricing",
            label="Configure Pricing",
            owner="settings",
            kind="navigation",
            risk="controlled",
            method="GET",
            endpoint="/settings/llm-profiles",
        ),
        RuntimeActionModel(
            id="disable_profile",
            label="Disable Profile",
            owner="llm",
            risk="dangerous",
            allowed=False,
            disabled_reason=(
                "LLM profile disable is not exposed as an operations action; "
                "update the configured profile source instead."
            ),
            requires_confirmation=True,
            reason_required=True,
        ),
    )


def _queue_rows(
    invocations: list[LlmInvocation],
    *,
    now: datetime,
) -> tuple[dict[str, str], ...]:
    sorted_invocations = sorted(
        invocations,
        key=lambda invocation: invocation.created_at,
        reverse=True,
    )
    return tuple(
        {
            "Priority": invocation.status.value,
            "Run ID": invocation.id,
            "Lane Key": invocation.llm_id,
            "Wait Reason": _invocation_reason(invocation),
            "Wait Time": _age_label(
                invocation.started_at or invocation.created_at,
                now=now,
            ),
        }
        for invocation in sorted_invocations[:20]
    )


def _profile_limit_rows(profiles: list[LlmProfile]) -> tuple[dict[str, str], ...]:
    limited_profiles = [
        profile
        for profile in profiles
        if profile.max_concurrency is not None or profile.concurrency_key is not None
    ]
    return tuple(
        {
            "Lane Key": profile.concurrency_key or f"provider:{profile.provider.value}",
            "Holder Run ID": profile.id,
            "TTL": f"{profile.timeout_seconds}s",
            "Expires At": (
                str(profile.max_concurrency)
                if profile.max_concurrency is not None
                else "-"
            ),
            "Reason": f"{profile.provider.value}/{profile.api_family.value}",
        }
        for profile in sorted(limited_profiles, key=lambda item: item.id)[:20]
    )


def _profile_rows(
    profiles: list[LlmProfile],
    invocations: list[LlmInvocation],
) -> tuple[dict[str, str], ...]:
    invocation_counts = Counter(invocation.llm_id for invocation in invocations)
    latest_invocation_by_profile: dict[str, LlmInvocation] = {}
    for invocation in sorted(invocations, key=lambda item: item.created_at, reverse=True):
        latest_invocation_by_profile.setdefault(invocation.llm_id, invocation)
    rows: list[dict[str, str]] = []
    for profile in sorted(profiles, key=lambda item: item.id):
        latest = latest_invocation_by_profile.get(profile.id)
        rows.append(
            {
                "Worker ID": profile.id,
                "Status": "enabled" if profile.enabled else "disabled",
                "Last Heartbeat": "-",
                "Current Run": latest.id if latest is not None else "-",
                "Load": str(invocation_counts[profile.id]),
            },
        )
    return tuple(rows[:20])


def _provider_access_health_section(
    profiles: list[LlmProfile],
    *,
    invocations: list[LlmInvocation],
    access_service: Any | None,
) -> OperationsTableSectionModel:
    invocation_counts = Counter(invocation.llm_id for invocation in invocations)
    latest_invocation = _latest_invocation_by_profile(invocations)
    rows: list[OperationsTableRowModel] = []
    for profile in sorted(profiles, key=lambda item: item.id):
        readiness = _profile_access_readiness(profile, access_service=access_service)
        latest = latest_invocation.get(profile.id)
        rows.append(
            OperationsTableRowModel(
                id=profile.id,
                cells={
                    "profile": profile.id,
                    "provider": profile.provider.value,
                    "model": profile.model_name,
                    "api_family": profile.api_family.value,
                    "credential": _credential_label(profile.credential_binding_id),
                    "status": _availability_label(profile, readiness),
                    "invocations": str(invocation_counts[profile.id]),
                    "last_invocation": (
                        format_datetime_utc(latest.created_at)
                        if latest is not None
                        else "-"
                    ),
                },
                status=readiness["status"],
                tone=_readiness_tone(readiness),
            ),
        )
    return OperationsTableSectionModel(
        id="provider_access_health",
        title="Provider Access & Health",
        columns=_columns(
            ("profile", "LLM Profile"),
            ("provider", "Provider"),
            ("model", "Model"),
            ("api_family", "API Family"),
            ("credential", "Credential"),
            ("status", "Status"),
            ("invocations", "Invocations"),
            ("last_invocation", "Last Invocation"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No LLM profiles configured.",
    )


def _provider_auth_blocked_section(
    profiles: list[LlmProfile],
    *,
    invocations: list[LlmInvocation],
    access_service: Any | None,
) -> OperationsTableSectionModel:
    invocation_counts = Counter(invocation.llm_id for invocation in invocations)
    rows: list[OperationsTableRowModel] = []
    for profile in sorted(profiles, key=lambda item: item.id):
        readiness = _profile_access_readiness(profile, access_service=access_service)
        if readiness["ready"]:
            continue
        rows.append(
            OperationsTableRowModel(
                id=profile.id,
                cells={
                    "profile": profile.id,
                    "provider": profile.provider.value,
                    "credential": _credential_label(profile.credential_binding_id),
                    "issue": readiness["reason"],
                    "affected_invocations": str(invocation_counts[profile.id]),
                    "action": "Open Access",
                },
                status=readiness["status"],
                tone=_readiness_tone(readiness),
            ),
        )
    return OperationsTableSectionModel(
        id="provider_auth_blocked",
        title="Provider Auth / Access Blocked",
        columns=_columns(
            ("profile", "LLM Profile"),
            ("provider", "Provider"),
            ("credential", "Credential"),
            ("issue", "Issue"),
            ("affected_invocations", "Affected Invocations"),
            ("action", "Action"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No provider access blockers.",
    )


def _model_resolver_section(
    resolver_events: tuple[OperationsObservedEvent, ...],
) -> OperationsChartSectionModel:
    counts = Counter(_resolver_bucket(event) for event in resolver_events)
    segments = tuple(
        OperationsChartSegmentModel(
            id=bucket,
            label=label,
            value=counts[bucket],
            tone=tone,
        )
        for bucket, label, tone in (
            ("agent_default", "Agent Default", "success"),
            ("explicit_override", "Explicit Override", "info"),
            ("fallback_used", "Fallback Used", "warning"),
            ("no_match", "No Match / Error", "danger"),
        )
        if counts[bucket]
    )
    return OperationsChartSectionModel(
        id="model_resolver",
        title="Model Resolver",
        kind="donut",
        total=sum(counts.values()),
        segments=segments,
    )


def _rate_limiter_section(
    profiles: list[LlmProfile],
    *,
    runtime_snapshot: dict[str, object],
) -> OperationsKeyValueSectionModel:
    active = _sum_metric_values(runtime_snapshot, section="gauges", name=_LLM_LIMITER_ACTIVE)
    waiters = _sum_metric_values(
        runtime_snapshot,
        section="gauges",
        name=_LLM_LIMITER_WAITERS,
    )
    timing = _combined_timing(runtime_snapshot, _LLM_LIMITER_WAIT_SECONDS)
    configured_capacity = sum(
        profile.max_concurrency or 0
        for profile in profiles
        if profile.max_concurrency is not None
    )
    constrained_profiles = sum(
        1 for profile in profiles if profile.max_concurrency is not None
    )
    return OperationsKeyValueSectionModel(
        id="rate_limiter",
        title="LLM Rate Limiter",
        items=(
            OperationsKeyValueItemModel(
                label="Active",
                value=str(int(active)),
                tone="info" if active else "neutral",
            ),
            OperationsKeyValueItemModel(
                label="Waiting",
                value=str(int(waiters)),
                tone="warning" if waiters else "success",
            ),
            OperationsKeyValueItemModel(
                label="Configured Capacity",
                value=str(configured_capacity),
                tone="neutral",
            ),
            OperationsKeyValueItemModel(
                label="Constrained Profiles",
                value=str(constrained_profiles),
                tone="neutral",
            ),
            OperationsKeyValueItemModel(
                label="Avg Wait",
                value=_seconds_label(timing["avg_seconds"]),
                tone="warning" if timing["avg_seconds"] > 0 else "success",
            ),
            OperationsKeyValueItemModel(
                label="Max Wait",
                value=_seconds_label(timing["max_seconds"]),
                tone="warning" if timing["max_seconds"] > 0 else "success",
            ),
        ),
    )


def _limiter_queue_section(
    profiles: list[LlmProfile],
    *,
    runtime_snapshot: dict[str, object],
) -> OperationsTableSectionModel:
    active_by_profile = _metric_values_by_label(
        runtime_snapshot,
        section="gauges",
        name=_LLM_LIMITER_ACTIVE,
        label="llm_id",
    )
    waiters_by_profile = _metric_values_by_label(
        runtime_snapshot,
        section="gauges",
        name=_LLM_LIMITER_WAITERS,
        label="llm_id",
    )
    wait_timing_by_profile = _timing_values_by_label(
        runtime_snapshot,
        name=_LLM_LIMITER_WAIT_SECONDS,
        label="llm_id",
    )
    rows: list[OperationsTableRowModel] = []
    for profile in sorted(profiles, key=lambda item: item.id):
        active = int(active_by_profile.get(profile.id, 0))
        waiters = int(waiters_by_profile.get(profile.id, 0))
        if profile.max_concurrency is None and not active and not waiters:
            continue
        timing = wait_timing_by_profile.get(
            profile.id,
            {"count": 0.0, "avg_seconds": 0.0, "max_seconds": 0.0},
        )
        saturated = (
            profile.max_concurrency is not None
            and active >= profile.max_concurrency
        )
        rows.append(
            OperationsTableRowModel(
                id=profile.id,
                cells={
                    "profile": profile.id,
                    "provider": profile.provider.value,
                    "concurrency_key": profile.concurrency_key or f"profile:{profile.id}",
                    "capacity": str(profile.max_concurrency or "-"),
                    "active": str(active),
                    "waiting": str(waiters),
                    "avg_wait": _seconds_label(timing["avg_seconds"]),
                    "max_wait": _seconds_label(timing["max_seconds"]),
                    "reason": (
                        "waiting for limiter slot"
                        if waiters
                        else "profile saturated"
                        if saturated
                        else "capacity available"
                    ),
                },
                status="waiting" if waiters else "saturated" if saturated else "available",
                tone="warning" if waiters or saturated else "success",
            ),
        )
    return OperationsTableSectionModel(
        id="limiter_queue",
        title="Limiter Queue",
        columns=_columns(
            ("profile", "LLM Profile"),
            ("provider", "Provider"),
            ("concurrency_key", "Concurrency Key"),
            ("capacity", "Capacity"),
            ("active", "Active"),
            ("waiting", "Waiting"),
            ("avg_wait", "Avg Wait"),
            ("max_wait", "Max Wait"),
            ("reason", "Reason"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No LLM limiter queue observed.",
    )


def _streaming_requests_section(
    streaming_invocations: list[LlmInvocation],
    *,
    profiles_by_id: dict[str, LlmProfile],
    events_by_invocation: dict[str, tuple[OperationsObservedEvent, ...]],
    run_contexts: dict[str, dict[str, str]],
    now: datetime,
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for invocation in sorted(
        streaming_invocations,
        key=lambda item: item.started_at or item.created_at,
        reverse=True,
    )[:50]:
        profile = profiles_by_id.get(invocation.llm_id)
        events = events_by_invocation.get(invocation.id, ())
        run_context = run_contexts.get(invocation.id, {})
        delta_count = sum(
            1
            for event in events
            if event.event_name in {"llm.stream_delta_observed", "orchestration.run.llm_text_delta"}
        )
        rows.append(
            OperationsTableRowModel(
                id=invocation.id,
                cells={
                    "started_at": _datetime_label(invocation.started_at),
                    "profile": invocation.llm_id,
                    "provider_model": _provider_model_label(profile),
                    "status": _stream_status_label(invocation, events=events, now=now),
                    "run_id": run_context.get("run_id", "-"),
                    "chain_id": run_context.get("chain_id", "-"),
                    "step_id": run_context.get("step_id", "-"),
                    "trace": run_context.get("trace_id", "-"),
                    "duration": _duration_or_age_label(invocation, now=now),
                    "tokens": str(_invocation_token_total(invocation)),
                    "events": str(delta_count),
                    "actions": "Open / Trace",
                    "route": run_context.get("route", "-"),
                    "trace_route": run_context.get("trace_route", "-"),
                },
                status=invocation.status.value,
                tone=_status_tone(invocation.status.value),
            ),
        )
    return OperationsTableSectionModel(
        id="streaming_requests",
        title="Streaming Requests",
        columns=_columns(
            ("started_at", "Started At"),
            ("profile", "LLM Profile"),
            ("provider_model", "Provider / Model"),
            ("status", "Status"),
            ("run_id", "Run ID"),
            ("chain_id", "Chain ID"),
            ("step_id", "Step ID"),
            ("trace", "Trace"),
            ("duration", "Duration"),
            ("tokens", "Tokens"),
            ("events", "Events"),
            ("actions", "Actions"),
        ),
        rows=tuple(rows),
        total=len(streaming_invocations),
        empty_state="No streaming LLM invocations observed.",
    )


def _recent_invocations_section(
    invocations: list[LlmInvocation],
    *,
    profiles_by_id: dict[str, LlmProfile],
    observed_events: tuple[OperationsObservedEvent, ...],
    events_by_invocation: dict[str, tuple[OperationsObservedEvent, ...]],
    run_contexts: dict[str, dict[str, str]],
    total_count: int,
    empty_state: str,
) -> OperationsTableSectionModel:
    streaming_ids = _streaming_invocation_ids(observed_events)
    rows: list[OperationsTableRowModel] = []
    for invocation in invocations:
        profile = profiles_by_id.get(invocation.llm_id)
        error_code = invocation.error.code if invocation.error is not None else "-"
        events = events_by_invocation.get(invocation.id, ())
        run_context = run_contexts.get(invocation.id, {})
        rows.append(
            OperationsTableRowModel(
                id=invocation.id,
                cells={
                    "time": format_datetime_utc(invocation.created_at),
                    "invocation_id": invocation.id,
                    "provider_model": _provider_model_label(profile),
                    "provider": profile.provider.value if profile is not None else "-",
                    "status": _status_label(invocation.status.value),
                    "run_id": run_context.get("run_id", "-"),
                    "chain_id": run_context.get("chain_id", "-"),
                    "step_id": run_context.get("step_id", "-"),
                    "trace": run_context.get("trace_id", "-"),
                    "duration": _duration_label(invocation),
                    "streaming": _stream_status_label(invocation, events=events, now=datetime.now(timezone.utc))
                    if invocation.id in streaming_ids
                    else "No",
                    "tokens": str(_invocation_token_total(invocation)),
                    "provider_prompt_tokens": _metadata_int_label(
                        invocation,
                        "estimated_provider_prompt_tokens",
                    ),
                    "direct_items": _metadata_int_label(
                        invocation,
                        "direct_session_item_count",
                    ),
                    "direct_tokens": _metadata_int_label(
                        invocation,
                        "direct_transcript_estimated_tokens",
                    ),
                    "tool_protocol": str(_direct_tool_protocol_count(invocation)),
                    "response_text": _response_text_label(invocation),
                    "tool_calls": _result_tool_calls_label(invocation),
                    "response_items": _response_item_count_label(invocation),
                    "response_events": "-",
                    "continuation": _continuation_reason_label(invocation),
                    "end_turn": _end_turn_label(invocation),
                    "progress": run_context.get("assistant_progress_item_count", "-"),
                    "finish_reason": (
                        invocation.result.finish_reason
                        if invocation.result is not None
                        and invocation.result.finish_reason
                        else "-"
                    ),
                    "error_code": error_code,
                    "actions": "Open / Trace",
                    "route": run_context.get("route", "-"),
                    "trace_route": run_context.get("trace_route", "-"),
                },
                status=invocation.status.value,
                tone=_status_tone(invocation.status.value),
            ),
        )
    return OperationsTableSectionModel(
        id="recent_invocations",
        title="Recent Invocations",
        columns=_columns(
            ("time", "Time"),
            ("invocation_id", "Invocation ID"),
            ("provider_model", "Provider / Model"),
            ("provider", "Provider"),
            ("status", "Status"),
            ("run_id", "Run ID"),
            ("chain_id", "Chain ID"),
            ("step_id", "Step ID"),
            ("trace", "Trace"),
            ("duration", "Duration"),
            ("streaming", "Streaming"),
            ("tokens", "Tokens"),
            ("provider_prompt_tokens", "Provider Prompt"),
            ("direct_items", "Direct Items"),
            ("direct_tokens", "Direct Tokens"),
            ("tool_protocol", "Tool Protocol"),
            ("response_text", "Text"),
            ("tool_calls", "Tool Calls"),
            ("response_items", "Items"),
            ("response_events", "Events"),
            ("continuation", "Continuation"),
            ("end_turn", "End Turn"),
            ("progress", "Progress"),
            ("finish_reason", "Finish Reason"),
            ("error_code", "Error Code"),
            ("actions", "Actions"),
        ),
        rows=tuple(rows),
        total=total_count,
        empty_state=empty_state,
    )


def _failed_invocations_section(
    failed_invocations: list[LlmInvocation],
    *,
    profiles_by_id: dict[str, LlmProfile],
    observed_events: tuple[OperationsObservedEvent, ...],
    events_by_invocation: dict[str, tuple[OperationsObservedEvent, ...]],
    run_contexts: dict[str, dict[str, str]],
    total_count: int,
    empty_state: str,
) -> OperationsTableSectionModel:
    streaming_ids = _streaming_invocation_ids(observed_events)
    rows: list[OperationsTableRowModel] = []
    for invocation in failed_invocations:
        profile = profiles_by_id.get(invocation.llm_id)
        events = events_by_invocation.get(invocation.id, ())
        run_context = run_contexts.get(invocation.id, {})
        rows.append(
            OperationsTableRowModel(
                id=invocation.id,
                cells={
                    "time": format_datetime_utc(invocation.created_at),
                    "invocation_id": invocation.id,
                    "provider_model": _provider_model_label(profile),
                    "status": _status_label(invocation.status.value),
                    "run_id": run_context.get("run_id", "-"),
                    "chain_id": run_context.get("chain_id", "-"),
                    "step_id": run_context.get("step_id", "-"),
                    "trace": run_context.get("trace_id", "-"),
                    "duration": _duration_label(invocation),
                    "streaming": _stream_status_label(invocation, events=events, now=datetime.now(timezone.utc))
                    if invocation.id in streaming_ids
                    else "No",
                    "error_code": invocation.error.code if invocation.error is not None else "-",
                    "actions": "Open / Trace",
                    "route": run_context.get("route", "-"),
                    "trace_route": run_context.get("trace_route", "-"),
                },
                status=invocation.status.value,
                tone=_status_tone(invocation.status.value),
            ),
        )
    return OperationsTableSectionModel(
        id="failed_invocations",
        title="Failed Invocations",
        columns=_columns(
            ("time", "Time"),
            ("invocation_id", "Invocation ID"),
            ("provider_model", "Provider / Model"),
            ("status", "Status"),
            ("run_id", "Run ID"),
            ("chain_id", "Chain ID"),
            ("step_id", "Step ID"),
            ("trace", "Trace"),
            ("duration", "Duration"),
            ("streaming", "Streaming"),
            ("error_code", "Error Code"),
            ("actions", "Actions"),
        ),
        rows=tuple(rows),
        total=total_count,
        empty_state=empty_state,
    )


def _latency_section(
    invocations: list[LlmInvocation],
    *,
    profiles_by_id: dict[str, LlmProfile],
) -> OperationsChartSectionModel:
    durations_by_provider: dict[str, list[float]] = defaultdict(list)
    for invocation in invocations:
        if invocation.status is not LlmInvocationStatus.SUCCEEDED:
            continue
        duration = _duration_seconds(invocation)
        if duration is None:
            continue
        profile = profiles_by_id.get(invocation.llm_id)
        key = profile.provider.value if profile is not None else invocation.llm_id
        durations_by_provider[key].append(duration)
    provider_averages = {
        key: sum(values) / len(values) for key, values in durations_by_provider.items()
    }
    total_average = (
        sum(provider_averages.values()) / len(provider_averages)
        if provider_averages
        else 0
    )
    return OperationsChartSectionModel(
        id="latency",
        title="Latency",
        kind="bar",
        total=int(total_average * 1000),
        segments=tuple(
            OperationsChartSegmentModel(
                id=provider,
                label=provider,
                value=int(seconds * 1000),
                tone=_chart_tone(index),
            )
            for index, (provider, seconds) in enumerate(
                sorted(provider_averages.items()),
            )
        ),
    )


def _token_usage_section(invocations: list[LlmInvocation]) -> OperationsChartSectionModel:
    input_tokens = 0
    output_tokens = 0
    reasoning_tokens = 0
    total_tokens = 0
    for invocation in invocations:
        if invocation.result is None or invocation.result.usage is None:
            continue
        usage = invocation.result.usage
        input_tokens += usage.input_tokens or 0
        output_tokens += usage.output_tokens or 0
        reasoning_tokens += usage.reasoning_tokens or 0
        total_tokens += (
            usage.total_tokens
            if usage.total_tokens is not None
            else (usage.input_tokens or 0) + (usage.output_tokens or 0)
        )
    unclassified = max(total_tokens - input_tokens - output_tokens - reasoning_tokens, 0)
    values = (
        ("input", "Input", input_tokens, "info"),
        ("output", "Output", output_tokens, "success"),
        ("reasoning", "Reasoning", reasoning_tokens, "warning"),
        ("unclassified", "Unclassified", unclassified, "neutral"),
    )
    return OperationsChartSectionModel(
        id="token_usage",
        title="Token Usage",
        kind="donut",
        total=total_tokens,
        segments=tuple(
            OperationsChartSegmentModel(id=id_, label=label, value=value, tone=tone)
            for id_, label, value, tone in values
            if value
        ),
    )


def _invocation_rate_section(
    invocations: list[LlmInvocation],
) -> OperationsChartSectionModel:
    counts = Counter(invocation.status.value for invocation in invocations)
    return OperationsChartSectionModel(
        id="invocation_rate",
        title="Invocation Rate",
        kind="donut",
        total=sum(counts.values()),
        segments=tuple(
            OperationsChartSegmentModel(
                id=status,
                label=_status_label(status),
                value=counts[status],
                tone=_status_tone(status),
            )
            for status in ("running", "succeeded", "failed", "created")
            if counts[status]
        ),
    )


def _stream_health_section(
    profiles: list[LlmProfile],
    *,
    streaming_invocations: list[LlmInvocation],
    observed_events: tuple[OperationsObservedEvent, ...],
    now: datetime,
) -> OperationsKeyValueSectionModel:
    active_streams = [
        invocation
        for invocation in streaming_invocations
        if invocation.status is LlmInvocationStatus.RUNNING
    ]
    completed_streams = [
        invocation
        for invocation in streaming_invocations
        if invocation.status is LlmInvocationStatus.SUCCEEDED
    ]
    failed_streams = [
        invocation
        for invocation in streaming_invocations
        if invocation.status is LlmInvocationStatus.FAILED
    ]
    delta_events = [
        event
        for event in observed_events
        if event.event_name in {"llm.stream_delta_observed", "orchestration.run.llm_text_delta"}
    ]
    longest_active = max(
        (
            _age_seconds(invocation.started_at or invocation.created_at, now=now)
            for invocation in active_streams
        ),
        default=0,
    )
    return OperationsKeyValueSectionModel(
        id="stream_health",
        title="Stream Health",
        items=(
            OperationsKeyValueItemModel(
                label="Active Streams",
                value=str(len(active_streams)),
                tone="info" if active_streams else "success",
            ),
            OperationsKeyValueItemModel(
                label="Completed Streams",
                value=str(len(completed_streams)),
                tone="success",
            ),
            OperationsKeyValueItemModel(
                label="Failed Streams",
                value=str(len(failed_streams)),
                tone="danger" if failed_streams else "success",
            ),
            OperationsKeyValueItemModel(
                label="Delta Events",
                value=str(len(delta_events)),
                tone="neutral",
            ),
            OperationsKeyValueItemModel(
                label="Longest Active",
                value=_seconds_label(longest_active),
                tone="warning" if longest_active >= _LONG_RUNNING_SECONDS else "neutral",
            ),
            OperationsKeyValueItemModel(
                label="Stream-capable Profiles",
                value=str(sum(1 for profile in profiles if _profile_supports_streaming(profile))),
                tone="neutral",
            ),
        ),
    )


def _execution_blocking_risk_section(
    profiles: list[LlmProfile],
    *,
    active_invocations: list[LlmInvocation],
    runtime_snapshot: dict[str, object],
    now: datetime,
) -> OperationsKeyValueSectionModel:
    waiters = _sum_metric_values(runtime_snapshot, section="gauges", name=_LLM_LIMITER_WAITERS)
    active_by_key = _metric_values_by_label(
        runtime_snapshot,
        section="gauges",
        name=_LLM_LIMITER_ACTIVE,
        label="concurrency_key",
    )
    saturated = 0
    for profile in profiles:
        if profile.max_concurrency is None:
            continue
        key = profile.concurrency_key or f"profile:{profile.id}"
        if active_by_key.get(key, 0) >= profile.max_concurrency:
            saturated += 1
    oldest_running = max(
        (
            _age_seconds(invocation.started_at or invocation.created_at, now=now)
            for invocation in active_invocations
        ),
        default=0,
    )
    return OperationsKeyValueSectionModel(
        id="execution_blocking_risk",
        title="Execution Blocking Risk",
        items=(
            OperationsKeyValueItemModel(
                label="Running Invocations",
                value=str(len(active_invocations)),
                tone="info" if active_invocations else "success",
            ),
            OperationsKeyValueItemModel(
                label="Limiter Waiters",
                value=str(int(waiters)),
                tone="warning" if waiters else "success",
            ),
            OperationsKeyValueItemModel(
                label="Saturated Profiles",
                value=str(saturated),
                tone="warning" if saturated else "success",
            ),
            OperationsKeyValueItemModel(
                label="Oldest Running",
                value=_seconds_label(oldest_running),
                tone="warning" if oldest_running >= _LONG_RUNNING_SECONDS else "neutral",
            ),
        ),
    )


def _fallback_problems_section(
    resolver_events: tuple[OperationsObservedEvent, ...],
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for event in resolver_events:
        bucket = _resolver_bucket(event)
        if bucket not in {"fallback_used", "no_match"}:
            continue
        payload = event.payload
        rows.append(
            OperationsTableRowModel(
                id=event.id,
                cells={
                    "time": format_datetime_utc(event.occurred_at),
                    "run_id": event.run_id or _text(payload.get("run_id")) or "-",
                    "requested": _text(payload.get("requested_llm_id")) or "-",
                    "resolved": _text(payload.get("resolved_llm_id")) or "-",
                    "strategy": _text(payload.get("strategy")) or bucket,
                    "reason": _text(payload.get("reason")) or _text(payload.get("error")) or "-",
                    "trace": event.trace_id or "-",
                },
                status=bucket,
                tone="danger" if bucket == "no_match" else "warning",
            ),
        )
    return OperationsTableSectionModel(
        id="fallback_problems",
        title="Fallback / Resolver Problems",
        columns=_columns(
            ("time", "Time"),
            ("run_id", "Run ID"),
            ("requested", "Requested"),
            ("resolved", "Resolved"),
            ("strategy", "Strategy"),
            ("reason", "Reason"),
            ("trace", "Trace"),
        ),
        rows=tuple(rows[:50]),
        total=len(rows),
        empty_state="No resolver fallback problems observed.",
    )


def _context_pressure_section(
    invocations: list[LlmInvocation],
    *,
    profiles_by_id: dict[str, LlmProfile],
) -> OperationsChartSectionModel:
    counts: Counter[str] = Counter()
    for invocation in invocations:
        profile = profiles_by_id.get(invocation.llm_id)
        if profile is None or not profile.context_window_tokens:
            continue
        input_tokens = _invocation_input_tokens(invocation) or _metadata_int(
            invocation,
            "estimated_provider_prompt_tokens",
        )
        if input_tokens <= 0:
            continue
        ratio = input_tokens / profile.context_window_tokens
        if ratio >= 0.9:
            counts["high"] += 1
        elif ratio >= 0.8:
            counts["elevated"] += 1
        else:
            counts["normal"] += 1
    return OperationsChartSectionModel(
        id="context_pressure",
        title="Context Window Pressure",
        kind="donut",
        total=sum(counts.values()),
        segments=tuple(
            OperationsChartSegmentModel(id=id_, label=label, value=counts[id_], tone=tone)
            for id_, label, tone in (
                ("normal", "<80%", "success"),
                ("elevated", "80-90%", "warning"),
                ("high", ">90%", "danger"),
            )
            if counts[id_]
        ),
    )


def _model_availability_section(
    profiles: list[LlmProfile],
    *,
    access_service: Any | None,
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for profile in sorted(profiles, key=lambda item: item.id):
        readiness = _profile_access_readiness(profile, access_service=access_service)
        availability = _availability_label(profile, readiness)
        rows.append(
            OperationsTableRowModel(
                id=profile.id,
                cells={
                    "profile": profile.id,
                    "provider": profile.provider.value,
                    "model": profile.model_name,
                    "availability": availability,
                    "context": _context_label(profile),
                    "max_concurrency": (
                        str(profile.max_concurrency)
                        if profile.max_concurrency is not None
                        else "-"
                    ),
                    "credential": _credential_label(profile.credential_binding_id),
                    "capabilities": _capability_label(profile),
                },
                status=readiness["status"],
                tone=_readiness_tone(readiness),
            ),
        )
    return OperationsTableSectionModel(
        id="model_availability",
        title="Model Availability",
        columns=_columns(
            ("profile", "LLM Profile"),
            ("provider", "Provider"),
            ("model", "Model"),
            ("availability", "Availability"),
            ("context", "Context"),
            ("max_concurrency", "Max Concurrency"),
            ("credential", "Credential"),
            ("capabilities", "Capabilities"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No LLM profiles configured.",
    )


def _error_summary_section(
    failed_invocations: list[LlmInvocation],
) -> OperationsTableSectionModel:
    by_category: dict[tuple[str, str], list[LlmInvocation]] = defaultdict(list)
    for invocation in failed_invocations:
        error_code = invocation.error.code if invocation.error is not None else "unknown"
        by_category[(_error_family(error_code), error_code)].append(invocation)
    rows: list[OperationsTableRowModel] = []
    for (category, error_code), items in sorted(
        by_category.items(),
        key=lambda item: (-len(item[1]), item[0]),
    ):
        latest = max(items, key=lambda item: item.completed_at or item.created_at)
        retryable = _retryable_error(category, error_code)
        rows.append(
            OperationsTableRowModel(
                id=f"{category}:{error_code}",
                cells={
                    "category": category,
                    "error_code": error_code,
                    "count": str(len(items)),
                    "retryable": "Yes" if retryable else "No",
                    "last_invocation": latest.id,
                    "last_failed": _datetime_label(latest.completed_at),
                    "reason": latest.error.message if latest.error is not None else "-",
                },
                status=category,
                tone="warning" if retryable else "danger",
            ),
        )
    return OperationsTableSectionModel(
        id="error_summary",
        title="Error Summary",
        columns=_columns(
            ("category", "Category"),
            ("error_code", "Error Code"),
            ("count", "Count"),
            ("retryable", "Retryable"),
            ("last_invocation", "Invocation ID"),
            ("last_failed", "Last Failed"),
            ("reason", "Reason"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No failed LLM invocations.",
    )


def _llm_lifecycle_events_section(
    observed_events: tuple[OperationsObservedEvent, ...],
) -> OperationsTableSectionModel:
    rows = tuple(
        OperationsTableRowModel(
            id=event.id,
            cells={
                "time": format_datetime_utc(event.occurred_at),
                "level": event.level,
                "event": event.event_name,
                "entity": event.entity_id,
                "status": event.status,
                "trace": event.trace_id or "-",
                "details": _json_preview(event.payload),
            },
            status=event.status,
            tone=_event_tone(event),
        )
        for event in observed_events[:80]
    )
    return OperationsTableSectionModel(
        id="llm_lifecycle_events",
        title="LLM Lifecycle Events",
        columns=_columns(
            ("time", "Time"),
            ("level", "Level"),
            ("event", "Event"),
            ("entity", "Entity"),
            ("status", "Status"),
            ("trace", "Trace"),
            ("details", "Details"),
        ),
        rows=rows,
        total=len(observed_events),
        empty_state="No LLM lifecycle events observed yet.",
    )


def _invocation_details(
    invocations: tuple[LlmInvocation, ...],
    *,
    profiles_by_id: dict[str, LlmProfile],
    events_by_invocation: dict[str, tuple[OperationsObservedEvent, ...]],
    run_contexts: dict[str, dict[str, str]],
    resolver_events_by_run_id: dict[str, OperationsObservedEvent],
    observed_events: tuple[OperationsObservedEvent, ...],
    response_events_by_invocation: dict[str, tuple[Any, ...]],
) -> tuple[LlmInvocationDetailModel, ...]:
    streaming_ids = _streaming_invocation_ids(observed_events)
    details: list[LlmInvocationDetailModel] = []
    for invocation in invocations:
        profile = profiles_by_id.get(invocation.llm_id)
        events = events_by_invocation.get(invocation.id, ())
        response_events = response_events_by_invocation.get(invocation.id, ())
        run_context = run_contexts.get(invocation.id, {})
        resolver_event = resolver_events_by_run_id.get(run_context.get("run_id", ""))
        error_code = invocation.error.code if invocation.error is not None else "-"
        category = _error_family(error_code) if invocation.error is not None else "-"
        details.append(
            LlmInvocationDetailModel(
                invocation_id=invocation.id,
                title=f"{invocation.llm_id} / {invocation.id}",
                status=invocation.status.value,
                tone=_status_tone(invocation.status.value),
                summary=(
                    OperationsKeyValueItemModel("Status", _status_label(invocation.status.value), _status_tone(invocation.status.value)),
                    OperationsKeyValueItemModel("Profile", invocation.llm_id),
                    OperationsKeyValueItemModel("Provider", profile.provider.value if profile is not None else "-"),
                    OperationsKeyValueItemModel("Model", profile.model_name if profile is not None else "-"),
                    OperationsKeyValueItemModel("Run ID", run_context.get("run_id", "-")),
                    OperationsKeyValueItemModel("Chain ID", run_context.get("chain_id", "-")),
                    OperationsKeyValueItemModel("Step ID", run_context.get("step_id", "-")),
                    OperationsKeyValueItemModel("Step Kind", run_context.get("step_kind", "-")),
                    OperationsKeyValueItemModel("Trace", run_context.get("trace_id", "-")),
                    OperationsKeyValueItemModel("Turn ID", run_context.get("turn_id", "-")),
                    OperationsKeyValueItemModel("Started At", _datetime_label(invocation.started_at)),
                    OperationsKeyValueItemModel("Completed At", _datetime_label(invocation.completed_at)),
                    OperationsKeyValueItemModel("Duration", _duration_label(invocation)),
                    OperationsKeyValueItemModel("Tokens", str(_invocation_token_total(invocation))),
                    OperationsKeyValueItemModel("Response Text", _response_text_label(invocation)),
                    OperationsKeyValueItemModel("Tool Calls", _result_tool_calls_label(invocation)),
                    OperationsKeyValueItemModel("Response Items", _response_item_count_label(invocation)),
                    OperationsKeyValueItemModel("Response Events", _response_event_count_label(response_events)),
                    OperationsKeyValueItemModel("Continuation", _continuation_reason_label(invocation)),
                    OperationsKeyValueItemModel("End Turn", _end_turn_label(invocation)),
                    OperationsKeyValueItemModel(
                        "Assistant Progress Items",
                        run_context.get("assistant_progress_item_count", "-"),
                    ),
                    OperationsKeyValueItemModel(
                        "Assistant Progress IDs",
                        run_context.get("assistant_progress_item_ids", "-"),
                    ),
                ),
                request_context=(
                    OperationsKeyValueItemModel(
                        "Streaming",
                        _stream_status_label(
                            invocation,
                            events=events,
                            now=datetime.now(timezone.utc),
                        )
                        if invocation.id in streaming_ids
                        else "No",
                    ),
                    OperationsKeyValueItemModel("Messages", str(len(invocation.messages))),
                    OperationsKeyValueItemModel("Tool Schemas", str(len(invocation.tool_schemas))),
                    OperationsKeyValueItemModel(
                        "Provider Prompt Tokens",
                        _metadata_int_label(
                            invocation,
                            "estimated_provider_prompt_tokens",
                        ),
                    ),
                    OperationsKeyValueItemModel(
                        "Direct Transcript Items",
                        _metadata_int_label(
                            invocation,
                            "direct_session_item_count",
                        ),
                    ),
                    OperationsKeyValueItemModel(
                        "Direct Transcript Tokens",
                        _metadata_int_label(
                            invocation,
                            "direct_transcript_estimated_tokens",
                        ),
                    ),
                    OperationsKeyValueItemModel(
                        "Tool Protocol Calls",
                        str(_direct_tool_protocol_count(invocation)),
                    ),
                    OperationsKeyValueItemModel(
                        "Artifact Tokens",
                        _metadata_int_label(
                            invocation,
                            "artifact_content_estimated_tokens",
                        ),
                    ),
                    OperationsKeyValueItemModel(
                        "Artifact Blocks",
                        _metadata_int_label(
                            invocation,
                            "artifact_content_block_count",
                        ),
                    ),
                    OperationsKeyValueItemModel(
                        "Artifact Omitted",
                        _metadata_int_label(
                            invocation,
                            "artifact_content_omitted_count",
                        ),
                    ),
                    OperationsKeyValueItemModel(
                        "Direct Sequence Range",
                        _direct_transcript_sequence_label(invocation),
                    ),
                    OperationsKeyValueItemModel(
                        "Context Snapshot",
                        _metadata_text_label(invocation, "context_render_snapshot_id"),
                    ),
                    OperationsKeyValueItemModel("Response Format", "Configured" if invocation.response_format else "-"),
                    OperationsKeyValueItemModel("Provider Request ID", invocation.provider_request_id or "-"),
                ),
                request_payload=_request_payload(invocation),
                result_payload=_result_payload(invocation),
                result_summary=_result_summary(invocation),
                error=invocation.error.message if invocation.error is not None else "",
                resolver=_resolver_facts_section(
                    invocation,
                    resolver_event=resolver_event,
                    run_context=run_context,
                ),
                error_facts=OperationsKeyValueSectionModel(
                    id="error_facts",
                    title="Error Facts",
                    items=(
                        OperationsKeyValueItemModel("Category", category, "danger" if category != "-" else "neutral"),
                        OperationsKeyValueItemModel("Error Code", error_code, "danger" if error_code != "-" else "neutral"),
                        OperationsKeyValueItemModel(
                            "Retryable",
                            "Yes" if _retryable_error(category, error_code) else "No",
                            "warning" if _retryable_error(category, error_code) else "neutral",
                        ),
                    ),
                ),
                policy_trace=_policy_trace_table_for_invocation(invocation),
                response_items=_response_items_table_for_invocation(invocation),
                response_events=_response_events_table_for_invocation(
                    invocation.id,
                    response_events,
                ),
                events=_events_table_for_invocation(invocation.id, events),
            ),
        )
    return tuple(details)


def _response_items_table_for_invocation(
    invocation: LlmInvocation,
) -> OperationsTableSectionModel:
    response_items = tuple(getattr(invocation, "response_items", ()) or ())
    rows = tuple(
        OperationsTableRowModel(
            id=str(getattr(item, "id", f"{invocation.id}:response_item:{index}")),
            cells={
                "sequence": str(getattr(item, "sequence_no", index)),
                "kind": _enum_value(getattr(item, "kind", None)),
                "phase": _enum_value(getattr(item, "phase", None)),
                "provider_type": str(getattr(item, "provider_item_type", None) or "-"),
                "tool": str(getattr(item, "tool_name", None) or "-"),
                "call_id": str(getattr(item, "call_id", None) or "-"),
                "model_visible": "Yes" if bool(getattr(item, "model_visible", False)) else "No",
                "user_visible": "Yes" if bool(getattr(item, "user_visible", False)) else "No",
                "content": _json_preview(getattr(item, "content_payload", {}) or {}),
            },
            status=_enum_value(getattr(item, "kind", None)),
            tone=_response_item_tone(_enum_value(getattr(item, "kind", None))),
        )
        for index, item in enumerate(response_items[:40], start=1)
    )
    return OperationsTableSectionModel(
        id=f"{invocation.id}_response_items",
        title="Response Items",
        columns=_columns(
            ("sequence", "Seq"),
            ("kind", "Kind"),
            ("phase", "Phase"),
            ("provider_type", "Provider Type"),
            ("tool", "Tool"),
            ("call_id", "Call ID"),
            ("model_visible", "Model Visible"),
            ("user_visible", "User Visible"),
            ("content", "Content"),
        ),
        rows=rows,
        total=len(response_items),
        empty_state="No response items recorded.",
    )


def _policy_trace_table_for_invocation(
    invocation: LlmInvocation,
) -> OperationsTableSectionModel:
    policy = _request_metadata(invocation).get("llm_request_policy")
    trace = policy.get("resolution_trace") if isinstance(policy, dict) else None
    rows = tuple(
        OperationsTableRowModel(
            id=f"{invocation.id}:policy_trace:{index}",
            cells={
                "field": _text(item.get("field")) or "-",
                "source": _text(item.get("source")) or "-",
                "status": _text(item.get("status")) or "-",
                "value": _json_preview(item.get("value")),
                "reason": _text(item.get("reason")) or "-",
            },
            status=_text(item.get("status")) or "-",
            tone=(
                "warning"
                if _text(item.get("status")) == "downgraded"
                else "neutral"
            ),
        )
        for index, item in enumerate(trace or (), start=1)
        if isinstance(item, dict)
    )
    return OperationsTableSectionModel(
        id=f"{invocation.id}_policy_trace",
        title="Policy Resolution Trace",
        columns=_columns(
            ("field", "Field"),
            ("source", "Source"),
            ("status", "Status"),
            ("value", "Value"),
            ("reason", "Reason"),
        ),
        rows=rows,
        total=len(rows),
        empty_state="No policy resolution trace recorded.",
    )


def _response_events_table_for_invocation(
    invocation_id: str,
    response_events: tuple[Any, ...],
) -> OperationsTableSectionModel:
    rows = tuple(
        OperationsTableRowModel(
            id=str(getattr(event, "id", f"{invocation_id}:response_event:{index}")),
            cells={
                "sequence": str(getattr(event, "sequence_no", index)),
                "type": _enum_value(getattr(event, "type", None)),
                "item_id": str(getattr(event, "item_id", None) or "-"),
                "provider_event": _provider_event_type(event),
                "delta": _json_preview(getattr(event, "delta_payload", {}) or {}),
            },
            status=_enum_value(getattr(event, "type", None)),
            tone=_response_event_tone(_enum_value(getattr(event, "type", None))),
        )
        for index, event in enumerate(response_events[:80], start=1)
    )
    return OperationsTableSectionModel(
        id=f"{invocation_id}_response_events",
        title="Response Events",
        columns=_columns(
            ("sequence", "Seq"),
            ("type", "Type"),
            ("item_id", "Item ID"),
            ("provider_event", "Provider Event"),
            ("delta", "Delta"),
        ),
        rows=rows,
        total=len(response_events),
        empty_state="No response events recorded.",
    )


def _events_table_for_invocation(
    invocation_id: str,
    events: tuple[OperationsObservedEvent, ...],
) -> OperationsTableSectionModel:
    rows = tuple(
        OperationsTableRowModel(
            id=event.id,
            cells={
                "time": format_datetime_utc(event.occurred_at),
                "level": event.level,
                "event": event.event_name,
                "status": event.status,
                "details": _json_preview(event.payload),
            },
            status=event.status,
            tone=_event_tone(event),
        )
        for event in events[:30]
    )
    return OperationsTableSectionModel(
        id=f"{invocation_id}_events",
        title="Invocation Events",
        columns=_columns(
            ("time", "Time"),
            ("level", "Level"),
            ("event", "Event"),
            ("status", "Status"),
            ("details", "Details"),
        ),
        rows=rows,
        total=len(events),
        empty_state="No observed events for this invocation.",
    )


def _filter_invocations(
    invocations: list[LlmInvocation],
    *,
    query: LlmOperationsQuery,
    profiles_by_id: dict[str, LlmProfile],
    observed_events: tuple[OperationsObservedEvent, ...],
    now: datetime,
) -> list[LlmInvocation]:
    streaming_ids = _streaming_invocation_ids(observed_events)
    result: list[LlmInvocation] = []
    search = query.search.strip().lower()
    for invocation in sorted(invocations, key=lambda item: item.created_at, reverse=True):
        if query.time_window == "24h" and coerce_utc_datetime(invocation.created_at) < now - _RECENT_WINDOW:
            continue
        if query.status != "all":
            if query.status == "active" and invocation.status is not LlmInvocationStatus.RUNNING:
                continue
            if query.status != "active" and invocation.status.value != query.status:
                continue
        if query.llm_id != "all" and invocation.llm_id != query.llm_id:
            continue
        profile = profiles_by_id.get(invocation.llm_id)
        if (
            query.provider != "all"
            and (profile is None or profile.provider.value != query.provider)
        ):
            continue
        if query.streaming != "all":
            streaming = invocation.id in streaming_ids
            if query.streaming == "yes" and not streaming:
                continue
            if query.streaming == "no" and streaming:
                continue
        if search and search not in _invocation_search_text(invocation, profile).lower():
            continue
        result.append(invocation)
    return result


def _normalize_query(query: LlmOperationsQuery | None) -> LlmOperationsQuery:
    if query is None:
        return LlmOperationsQuery()
    return LlmOperationsQuery(
        status=query.status if query.status else "all",
        time_window=query.time_window if query.time_window in {"all", "24h"} else "all",
        search=query.search or "",
        llm_id=query.llm_id or "all",
        provider=query.provider or "all",
        streaming=query.streaming if query.streaming in {"all", "yes", "no"} else "all",
        limit=max(min(int(query.limit), 200), 1),
        offset=max(int(query.offset), 0),
    )


def _invocation_page_read_limit(query: LlmOperationsQuery) -> int:
    requested_window = query.offset + query.limit
    return max(requested_window, _INVOCATION_PAGE_BASE_LIMIT)


def _paginate_invocations(
    invocations: list[LlmInvocation],
    *,
    query: LlmOperationsQuery,
) -> list[LlmInvocation]:
    return invocations[query.offset : query.offset + query.limit]


def _invocations_empty_state(query: LlmOperationsQuery) -> str:
    if _has_invocation_filters(query):
        return "No LLM invocations match the current filters."
    return "No LLM invocations recorded yet."


def _has_invocation_filters(query: LlmOperationsQuery) -> bool:
    return any(
        (
            query.status != "all",
            query.time_window != "all",
            query.search.strip(),
            query.llm_id != "all",
            query.provider != "all",
            query.streaming != "all",
        ),
    )


def _streaming_invocations(
    invocations: list[LlmInvocation],
    *,
    profiles_by_id: dict[str, LlmProfile],
    observed_events: tuple[OperationsObservedEvent, ...],
) -> list[LlmInvocation]:
    streaming_ids = _streaming_invocation_ids(observed_events)
    return [
        invocation
        for invocation in invocations
        if invocation.id in streaming_ids
        or (
            invocation.status is LlmInvocationStatus.RUNNING
            and _profile_supports_streaming(profiles_by_id.get(invocation.llm_id))
        )
    ]


def _streaming_invocation_ids(
    observed_events: tuple[OperationsObservedEvent, ...],
) -> set[str]:
    ids: set[str] = set()
    for event in observed_events:
        payload = event.payload
        invocation_id = _text(payload.get("invocation_id")) or event.entity_id
        if not invocation_id:
            continue
        if _bool(payload.get("streaming")) or event.event_name == "llm.stream_delta_observed":
            ids.add(invocation_id)
    return ids


def _recent_llm_events(
    *,
    operations_observation: OperationsObservationReadPort | None,
    events_service: Any | None,
    definition_registry: Any | None,
    limit: int,
) -> tuple[OperationsObservedEvent, ...]:
    event_limit = max(int(limit), 1)
    return _dedupe_llm_events(
        (
            *_recent_llm_events_from_bus(
                events_service,
                definition_registry=definition_registry,
                limit=event_limit,
            ),
            *_recent_llm_events_from_observation(
                operations_observation,
                limit=event_limit,
            ),
        ),
        limit=event_limit,
    )


def _recent_llm_events_from_observation(
    operations_observation: OperationsObservationReadPort | None,
    *,
    limit: int,
) -> tuple[OperationsObservedEvent, ...]:
    if operations_observation is None:
        return ()
    try:
        observation = operations_observation.get_module_observation("llm")
    except Exception:
        return ()
    if observation is None:
        return ()
    recent_events = getattr(observation, "recent_events", ())
    return tuple(
        event for event in recent_events if isinstance(event, OperationsObservedEvent)
    )[:limit]


def _recent_resolver_events(
    *,
    operations_observation: OperationsObservationReadPort | None,
    events_service: Any | None,
    definition_registry: Any | None,
    limit: int,
) -> tuple[OperationsObservedEvent, ...]:
    event_limit = max(int(limit), 1)
    return _dedupe_llm_events(
        (
            *_recent_resolver_events_from_bus(
                events_service,
                definition_registry=definition_registry,
                limit=event_limit,
            ),
            *_recent_resolver_events_from_observation(
                operations_observation,
                limit=event_limit,
            ),
        ),
        limit=event_limit,
    )


def _recent_resolver_events_from_observation(
    operations_observation: OperationsObservationReadPort | None,
    *,
    limit: int,
) -> tuple[OperationsObservedEvent, ...]:
    if operations_observation is None:
        return ()
    events: list[OperationsObservedEvent] = []
    for module in ("orchestration", "llm"):
        try:
            observation = operations_observation.get_module_observation(module)
        except Exception:
            continue
        if observation is None:
            continue
        events.extend(
            event
            for event in getattr(observation, "recent_events", ())
            if isinstance(event, OperationsObservedEvent)
            and event.event_name == "orchestration.llm_resolved"
        )
    return tuple(sorted(events, key=lambda event: event.occurred_at, reverse=True))[:limit]


def _recent_llm_events_from_bus(
    events_service: Any | None,
    *,
    definition_registry: Any | None,
    limit: int,
) -> tuple[OperationsObservedEvent, ...]:
    return _recent_observed_events_from_bus(
        events_service,
        definition_registry=definition_registry,
        seed_topics=_LLM_DIRECT_EVENT_TOPICS,
        topic_filter=_is_llm_event_topic,
        event_filter=_is_llm_observed_event,
        limit=limit,
    )


def _recent_resolver_events_from_bus(
    events_service: Any | None,
    *,
    definition_registry: Any | None,
    limit: int,
) -> tuple[OperationsObservedEvent, ...]:
    return _recent_observed_events_from_bus(
        events_service,
        definition_registry=definition_registry,
        seed_topics=_LLM_RESOLVER_EVENT_TOPICS,
        topic_filter=_is_resolver_event_topic,
        event_filter=_is_resolver_observed_event,
        limit=limit,
    )


def _recent_observed_events_from_bus(
    events_service: Any | None,
    *,
    definition_registry: Any | None,
    seed_topics: tuple[str, ...] = (),
    topic_filter: Any,
    event_filter: Any,
    limit: int,
) -> tuple[OperationsObservedEvent, ...]:
    if events_service is None:
        return ()
    topics = _dedupe_topic_names(
        (
            *seed_topics,
            *(
                topic
                for topic in _safe_list_event_topics(events_service)
                if topic_filter(topic)
            ),
        ),
    )[:_MAX_LLM_EVENT_TOPICS]
    read_recent = getattr(events_service, "read_recent_event_topic", None)
    if not callable(read_recent):
        return ()
    events: list[OperationsObservedEvent] = []
    topic_limit = min(max(_RECENT_LLM_TOPIC_LIMIT, int(limit)), _MAX_RECENT_LLM_EVENTS)
    for topic in topics:
        try:
            records = tuple(read_recent(topic, limit=topic_limit) or ())
        except Exception:
            continue
        for record in records:
            try:
                observed = observed_event_from_record(
                    record,
                    definition_registry=definition_registry,
                )
            except Exception:
                continue
            if event_filter(observed):
                events.append(observed)
    events.sort(key=lambda event: coerce_utc_datetime(event.occurred_at), reverse=True)
    return tuple(events[:_MAX_RECENT_LLM_EVENTS])


def _safe_list_event_topics(events_service: Any) -> tuple[str, ...]:
    list_topics = getattr(events_service, "list_event_topics", None)
    if not callable(list_topics):
        return ()
    try:
        return tuple(str(topic) for topic in list_topics() or () if str(topic))
    except Exception:
        return ()


def _dedupe_topic_names(topics: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for topic in topics:
        normalized = topic.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return tuple(result)


def _is_llm_event_topic(topic: str) -> bool:
    normalized = topic.strip().lower()
    return (
        normalized.startswith("llm.")
        or normalized.startswith("events.named.llm.")
        or normalized == "orchestration.run.llm_text_delta"
        or normalized == "events.named.orchestration.run.llm_text_delta"
    )


def _is_llm_observed_event(event: OperationsObservedEvent) -> bool:
    owner = event.owner.strip().lower()
    module = event.module.strip().lower()
    event_name = event.event_name.strip().lower()
    return (
        owner == "llm"
        or module == "llm"
        or event_name.startswith("llm.")
        or event_name == "orchestration.run.llm_text_delta"
    )


def _is_resolver_event_topic(topic: str) -> bool:
    normalized = topic.strip().lower()
    return (
        normalized == "orchestration.llm_resolved"
        or normalized == "events.named.orchestration.llm_resolved"
    )


def _is_resolver_observed_event(event: OperationsObservedEvent) -> bool:
    return event.event_name.strip().lower() == "orchestration.llm_resolved"


def _dedupe_llm_events(
    events: tuple[OperationsObservedEvent, ...],
    *,
    limit: int,
) -> tuple[OperationsObservedEvent, ...]:
    result: list[OperationsObservedEvent] = []
    seen: set[tuple[str, str]] = set()
    for event in sorted(
        events,
        key=lambda item: coerce_utc_datetime(item.occurred_at),
        reverse=True,
    ):
        key = (event.topic, event.cursor or event.id)
        if key in seen:
            continue
        seen.add(key)
        result.append(event)
    return tuple(result[: min(max(int(limit), 1), _MAX_RECENT_LLM_EVENTS)])


def _events_by_invocation(
    events: tuple[OperationsObservedEvent, ...],
) -> dict[str, tuple[OperationsObservedEvent, ...]]:
    grouped: dict[str, list[OperationsObservedEvent]] = defaultdict(list)
    for event in events:
        invocation_id = (
            _text(event.payload.get("invocation_id"))
            or _text(event.payload.get("llm_invocation_id"))
            or (
                event.entity_id
                if event.event_name.startswith("llm.invocation")
                or event.event_name == "llm.stream_delta_observed"
                else None
            )
        )
        if invocation_id:
            grouped[invocation_id].append(event)
    return {
        key: tuple(sorted(items, key=lambda event: event.occurred_at, reverse=True))
        for key, items in grouped.items()
    }


def _response_events_by_invocation(
    llm_service: OperationsLlmQueryPort,
    invocations: tuple[LlmInvocation, ...],
) -> dict[str, tuple[Any, ...]]:
    list_response_events = getattr(llm_service, "list_response_events", None)
    if not callable(list_response_events):
        return {}
    grouped: dict[str, tuple[Any, ...]] = {}
    for invocation in invocations:
        try:
            events = list_response_events(invocation.id, limit=100)
        except Exception:
            events = []
        grouped[invocation.id] = tuple(events)
    return grouped


def _runtime_snapshot(runtime_metrics: Any | None) -> dict[str, object]:
    if runtime_metrics is None or not hasattr(runtime_metrics, "snapshot"):
        return {"counters": [], "gauges": [], "timings": []}
    try:
        snapshot = runtime_metrics.snapshot(prefixes=(_LLM_LIMITER_PREFIX,))
    except Exception:
        return {"counters": [], "gauges": [], "timings": []}
    return snapshot if isinstance(snapshot, dict) else {"counters": [], "gauges": [], "timings": []}


def _sum_metric_values(
    runtime_snapshot: dict[str, object],
    *,
    section: str,
    name: str,
) -> float:
    total = 0.0
    raw_items = runtime_snapshot.get(section)
    if not isinstance(raw_items, list):
        return total
    for item in raw_items:
        if not isinstance(item, dict) or item.get("name") != name:
            continue
        total += _float(item.get("value"))
    return total


def _metric_values_by_label(
    runtime_snapshot: dict[str, object],
    *,
    section: str,
    name: str,
    label: str,
) -> dict[str, float]:
    values: dict[str, float] = {}
    raw_items = runtime_snapshot.get(section)
    if not isinstance(raw_items, list):
        return values
    for item in raw_items:
        if not isinstance(item, dict) or item.get("name") != name:
            continue
        labels = item.get("labels")
        if not isinstance(labels, dict):
            continue
        key = _text(labels.get(label))
        if key is None:
            continue
        values[key] = values.get(key, 0.0) + _float(item.get("value"))
    return values


def _timing_values_by_label(
    runtime_snapshot: dict[str, object],
    *,
    name: str,
    label: str,
) -> dict[str, dict[str, float]]:
    values: dict[str, dict[str, float]] = {}
    raw_items = runtime_snapshot.get("timings")
    if not isinstance(raw_items, list):
        return values
    for item in raw_items:
        if not isinstance(item, dict) or item.get("name") != name:
            continue
        labels = item.get("labels")
        if not isinstance(labels, dict):
            continue
        key = _text(labels.get(label))
        if key is None:
            continue
        bucket = values.setdefault(
            key,
            {"count": 0.0, "total_seconds": 0.0, "max_seconds": 0.0},
        )
        item_count = _float(item.get("count"))
        bucket["count"] += item_count
        bucket["total_seconds"] += _float(item.get("total_seconds"))
        bucket["max_seconds"] = max(
            bucket["max_seconds"],
            _float(item.get("max_seconds")),
        )
    return {
        key: {
            "count": bucket["count"],
            "avg_seconds": (
                bucket["total_seconds"] / bucket["count"]
                if bucket["count"]
                else 0.0
            ),
            "max_seconds": bucket["max_seconds"],
        }
        for key, bucket in values.items()
    }


def _combined_timing(
    runtime_snapshot: dict[str, object],
    name: str,
) -> dict[str, float]:
    count = 0
    total_seconds = 0.0
    max_seconds = 0.0
    raw_items = runtime_snapshot.get("timings")
    if not isinstance(raw_items, list):
        return {"count": 0, "avg_seconds": 0.0, "max_seconds": 0.0}
    for item in raw_items:
        if not isinstance(item, dict) or item.get("name") != name:
            continue
        item_count = int(_float(item.get("count")))
        count += item_count
        total_seconds += _float(item.get("total_seconds"))
        max_seconds = max(max_seconds, _float(item.get("max_seconds")))
    return {
        "count": float(count),
        "avg_seconds": total_seconds / count if count else 0.0,
        "max_seconds": max_seconds,
    }


def _limiter_waiter_count(runtime_snapshot: dict[str, object]) -> int:
    return int(_sum_metric_values(runtime_snapshot, section="gauges", name=_LLM_LIMITER_WAITERS))


def _blocked_profiles(
    profiles: list[LlmProfile],
    *,
    access_service: Any | None,
) -> list[LlmProfile]:
    return [
        profile
        for profile in profiles
        if not _profile_access_readiness(profile, access_service=access_service)["ready"]
    ]


def _profile_access_readiness(
    profile: LlmProfile,
    *,
    access_service: Any | None,
) -> dict[str, Any]:
    if not profile.enabled:
        return {
            "ready": False,
            "status": "disabled",
            "reason": "profile is disabled",
        }
    if not profile.credential_binding_id:
        if profile.provider.value == "ollama":
            return {
                "ready": True,
                "status": "ready",
                "reason": "local provider does not require a credential binding",
            }
        return {
            "ready": False,
            "status": "setup_needed",
            "reason": "profile has no access credential binding id",
        }
    if access_service is None or not hasattr(access_service, "check_credential_binding"):
        return {
            "ready": False,
            "status": "unknown",
            "reason": "access readiness service is not connected",
        }
    try:
        readiness = access_service.check_credential_binding(profile.credential_binding_id)
    except Exception as exc:
        return {
            "ready": False,
            "status": "error",
            "reason": str(exc) or type(exc).__name__,
        }
    return {
        "ready": bool(getattr(readiness, "ready", False)),
        "status": getattr(getattr(readiness, "status", None), "value", None)
        or str(getattr(readiness, "status", "unknown")),
        "reason": str(getattr(readiness, "reason", "")) or "access readiness unknown",
    }


def _readiness_tone(readiness: dict[str, Any]) -> str:
    if readiness.get("ready"):
        return "success"
    status = str(readiness.get("status") or "")
    if status in {"setup_needed", "waiting_user", "unknown", "disabled"}:
        return "warning"
    return "danger"


def _availability_label(profile: LlmProfile, readiness: dict[str, Any]) -> str:
    if not profile.enabled:
        return "Disabled"
    if readiness.get("ready"):
        return "Available"
    status = str(readiness.get("status") or "unknown")
    if status == "setup_needed":
        return "Auth Required"
    if status == "unsupported":
        return "Unsupported"
    if status == "unknown":
        return "Unknown"
    return "Blocked"


def _latest_invocation_by_profile(
    invocations: list[LlmInvocation],
) -> dict[str, LlmInvocation]:
    latest: dict[str, LlmInvocation] = {}
    for invocation in sorted(invocations, key=lambda item: item.created_at, reverse=True):
        latest.setdefault(invocation.llm_id, invocation)
    return latest


def _invocation_run_contexts(
    run_query: Any | None,
    invocations: list[LlmInvocation],
) -> dict[str, dict[str, str]]:
    if run_query is None or not hasattr(run_query, "find_execution_step_items_by_owner"):
        return {}
    contexts: dict[str, dict[str, str]] = {}
    for invocation in invocations:
        context = _execution_owner_context(
            run_query,
            ExecutionOwnerReference(
                owner_kind="llm_invocation",
                owner_id=invocation.id,
            ),
        )
        if not context:
            continue
        existing = contexts.get(invocation.id)
        if existing is None or context.get("updated_at", "") > existing.get("updated_at", ""):
            contexts[invocation.id] = context
    return {
        invocation_id: {
            key: value
            for key, value in context.items()
            if key != "updated_at"
        }
        for invocation_id, context in contexts.items()
    }


def _execution_owner_context(
    run_query: Any,
    owner: ExecutionOwnerReference,
) -> dict[str, str] | None:
    try:
        items = run_query.find_execution_step_items_by_owner(owner)
    except Exception:
        return None
    if not items:
        return None
    item = max(items, key=_execution_item_updated_at)
    try:
        step = run_query.get_execution_step(item.step_id)
    except Exception:
        step = None
    try:
        run = run_query.get_run(item.turn_id)
    except Exception:
        run = None
    run_id = _text(getattr(run, "id", None)) or _text(getattr(item, "turn_id", None))
    if run_id is None:
        return None
    metadata = getattr(run, "metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    trace_id = _text(metadata.get("trace_id")) or run_id
    return {
        "run_id": run_id,
        "turn_id": _text(metadata.get("turn_id")) or item.turn_id,
        "trace_id": trace_id,
        "session_key": _text(metadata.get("session_key")) or "-",
        "route": f"/ui/workbench/runs/{run_id}",
        "trace_route": f"/ui/trace/{trace_id}?step_id={item.step_id}",
        "chain_id": item.chain_id,
        "step_id": item.step_id,
        "step_kind": _enum_value(getattr(step, "kind", None)),
        "step_status": _enum_value(getattr(step, "status", None)),
        "item_status": _enum_value(getattr(item, "status", None)),
        **_llm_execution_summary_context(getattr(item, "summary_payload", None)),
        "updated_at": _execution_item_updated_at(item),
    }


def _llm_execution_summary_context(summary_payload: Any) -> dict[str, str]:
    if not isinstance(summary_payload, dict):
        return {}
    progress_ids = _text_list(summary_payload.get("assistant_progress_item_ids"))
    result: dict[str, str] = {}
    if progress_ids:
        result["assistant_progress_item_ids"] = ", ".join(progress_ids)
        result["assistant_progress_item_count"] = str(len(progress_ids))
    progress_text = _text(summary_payload.get("assistant_progress_text"))
    if progress_text is not None:
        result["assistant_progress_text"] = _truncate(progress_text, 160)
    tool_call_names = _text_list(summary_payload.get("tool_call_names"))
    if tool_call_names:
        result["tool_call_names"] = ", ".join(tool_call_names)
        result["tool_call_count"] = str(len(tool_call_names))
    return result


def _execution_item_updated_at(item: Any) -> str:
    updated_at = getattr(item, "updated_at", None)
    if isinstance(updated_at, datetime):
        return format_datetime_utc(updated_at)
    return str(updated_at or "")


def _enum_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    if raw is None:
        return "-"
    normalized = str(raw).strip()
    return normalized or "-"


def _resolver_events_by_run_id(
    resolver_events: tuple[OperationsObservedEvent, ...],
) -> dict[str, OperationsObservedEvent]:
    result: dict[str, OperationsObservedEvent] = {}
    for event in resolver_events:
        run_id = _text(event.payload.get("run_id"))
        if run_id is None:
            continue
        result.setdefault(run_id, event)
    return result


def _resolver_bucket(event: OperationsObservedEvent) -> str:
    payload = event.payload
    requested = _text(payload.get("requested_llm_id"))
    resolved = _text(payload.get("resolved_llm_id"))
    strategy = (
        _text(payload.get("strategy"))
        or _text(payload.get("resolution_strategy"))
        or _text(payload.get("resolved_by"))
        or ""
    ).lower()
    status = event.status.lower()
    if status in {"failed", "error"} or not resolved:
        return "no_match"
    if requested and resolved and requested != resolved:
        return "fallback_used"
    if "override" in strategy or "explicit" in strategy:
        return "explicit_override"
    return "agent_default"


def _resolver_facts_section(
    invocation: LlmInvocation,
    *,
    resolver_event: OperationsObservedEvent | None,
    run_context: dict[str, str],
) -> OperationsKeyValueSectionModel:
    if resolver_event is None:
        return OperationsKeyValueSectionModel(
            id="resolver",
            title="Resolver Decision",
            items=(
                OperationsKeyValueItemModel("Requested", "-"),
                OperationsKeyValueItemModel("Resolved", invocation.llm_id),
                OperationsKeyValueItemModel("Strategy", "-"),
                OperationsKeyValueItemModel("Run ID", run_context.get("run_id", "-")),
            ),
        )
    payload = resolver_event.payload
    bucket = _resolver_bucket(resolver_event)
    return OperationsKeyValueSectionModel(
        id="resolver",
        title="Resolver Decision",
        items=(
            OperationsKeyValueItemModel(
                "Requested",
                _text(payload.get("requested_llm_id")) or "-",
            ),
            OperationsKeyValueItemModel(
                "Resolved",
                _text(payload.get("resolved_llm_id")) or "-",
                "success" if _text(payload.get("resolved_llm_id")) else "danger",
            ),
            OperationsKeyValueItemModel(
                "Strategy",
                _text(payload.get("strategy")) or "-",
            ),
            OperationsKeyValueItemModel(
                "Decision",
                {
                    "agent_default": "Agent Default",
                    "explicit_override": "Explicit Override",
                    "fallback_used": "Fallback Used",
                    "no_match": "No Match / Error",
                }.get(bucket, bucket),
                {
                    "agent_default": "success",
                    "explicit_override": "info",
                    "fallback_used": "warning",
                    "no_match": "danger",
                }.get(bucket, "neutral"),
            ),
            OperationsKeyValueItemModel(
                "Reason",
                _text(payload.get("reason")) or "-",
                "warning" if _text(payload.get("reason")) else "neutral",
            ),
            OperationsKeyValueItemModel(
                "Run ID",
                _text(payload.get("run_id")) or run_context.get("run_id", "-"),
            ),
        ),
    )


def _invocation_reason(invocation: LlmInvocation) -> str:
    if invocation.error is not None:
        return f"{invocation.error.code}: {invocation.error.message}"
    if invocation.result is not None and invocation.result.finish_reason:
        return invocation.result.finish_reason
    return invocation.status.value


def _token_total(invocations: list[LlmInvocation]) -> int:
    total = 0
    for invocation in invocations:
        total += _invocation_token_total(invocation)
    return total


def _invocation_token_total(invocation: LlmInvocation) -> int:
    if invocation.result is None or invocation.result.usage is None:
        return 0
    usage = invocation.result.usage
    if usage.total_tokens is not None:
        return usage.total_tokens
    return (usage.input_tokens or 0) + (usage.output_tokens or 0)


def _invocation_input_tokens(invocation: LlmInvocation) -> int:
    if invocation.result is None or invocation.result.usage is None:
        return 0
    return invocation.result.usage.input_tokens or 0


def _request_metadata(invocation: LlmInvocation) -> dict[str, object]:
    metadata = invocation.request_metadata
    return metadata if isinstance(metadata, dict) else {}


def _metadata_int(invocation: LlmInvocation, key: str) -> int:
    value = _request_metadata(invocation).get(key)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    if isinstance(value, str):
        try:
            return max(int(value), 0)
        except ValueError:
            return 0
    return 0


def _metadata_int_label(invocation: LlmInvocation, key: str) -> str:
    return str(value) if (value := _metadata_int(invocation, key)) else "-"


def _metadata_text_label(invocation: LlmInvocation, key: str) -> str:
    value = _text(_request_metadata(invocation).get(key))
    return value or "-"


def _direct_tool_protocol_count(invocation: LlmInvocation) -> int:
    value = _request_metadata(invocation).get("direct_tool_protocol_call_ids")
    if isinstance(value, (list, tuple)):
        return len([item for item in value if str(item or "").strip()])
    return 0


def _response_text_label(invocation: LlmInvocation) -> str:
    text = getattr(getattr(invocation, "result", None), "text", None)
    if isinstance(text, str) and text.strip():
        return f"{len(text.strip())} chars"
    return "-"


def _result_tool_calls_label(invocation: LlmInvocation) -> str:
    tool_calls = getattr(getattr(invocation, "result", None), "tool_calls", None)
    if isinstance(tool_calls, (list, tuple)) and tool_calls:
        return str(len(tool_calls))
    return "-"


def _response_item_count_label(invocation: LlmInvocation) -> str:
    response_items = getattr(invocation, "response_items", None)
    if isinstance(response_items, (list, tuple)) and response_items:
        return str(len(response_items))
    return "-"


def _response_event_count_label(response_events: tuple[Any, ...]) -> str:
    return str(len(response_events)) if response_events else "-"


def _continuation_reason_label(invocation: LlmInvocation) -> str:
    continuation = getattr(invocation, "continuation", None)
    reason = getattr(continuation, "reason", None)
    return _enum_value(reason) if reason is not None else "-"


def _end_turn_label(invocation: LlmInvocation) -> str:
    continuation = getattr(invocation, "continuation", None)
    end_turn = getattr(continuation, "end_turn", None)
    if end_turn is True:
        return "Yes"
    if end_turn is False:
        return "No"
    return "-"


def _direct_transcript_sequence_label(invocation: LlmInvocation) -> str:
    sequence_range = _request_metadata(invocation).get("direct_transcript_sequence_range")
    if not isinstance(sequence_range, dict):
        return "-"
    sessions = sequence_range.get("sessions")
    if not isinstance(sessions, list) or not sessions:
        return "-"
    labels: list[str] = []
    for item in sessions[:3]:
        if not isinstance(item, dict):
            continue
        session_id = _text(item.get("session_id")) or "session"
        from_sequence = _text(item.get("from_sequence_no")) or "?"
        to_sequence = _text(item.get("to_sequence_no")) or "?"
        item_count = _text(item.get("item_count")) or "?"
        labels.append(f"{session_id}:{from_sequence}-{to_sequence} ({item_count})")
    if not labels:
        return "-"
    if len(sessions) > 3:
        labels.append(f"+{len(sessions) - 3}")
    return ", ".join(labels)


def _max_context_label(profiles: list[LlmProfile]) -> str:
    values = [
        profile.context_window_tokens
        for profile in profiles
        if profile.context_window_tokens is not None
    ]
    if not values:
        return "-"
    return str(max(values))


def _context_label(profile: LlmProfile) -> str:
    return str(profile.context_window_tokens) if profile.context_window_tokens else "-"


def _capability_label(profile: LlmProfile) -> str:
    if not profile.capabilities:
        return "-"
    return ", ".join(capability.value for capability in profile.capabilities)


def _profile_supports_streaming(profile: LlmProfile | None) -> bool:
    if profile is None:
        return False
    return any(capability.value == "streaming" for capability in profile.capabilities)


def _provider_model_label(profile: LlmProfile | None) -> str:
    if profile is None:
        return "-"
    return f"{profile.provider.value} / {profile.model_name}"


def _credential_label(value: str | None) -> str:
    if value is None or not value.strip():
        return "-"
    return value.strip()


def _duration_seconds(invocation: LlmInvocation) -> float | None:
    if invocation.started_at is None or invocation.completed_at is None:
        return None
    return max(
        (
            coerce_utc_datetime(invocation.completed_at)
            - coerce_utc_datetime(invocation.started_at)
        ).total_seconds(),
        0.0,
    )


def _duration_label(invocation: LlmInvocation) -> str:
    duration = _duration_seconds(invocation)
    return _seconds_label(duration)


def _duration_or_age_label(invocation: LlmInvocation, *, now: datetime) -> str:
    duration = _duration_seconds(invocation)
    if duration is not None:
        return _seconds_label(duration)
    return _age_label(invocation.started_at or invocation.created_at, now=now)


def _age_label(value: datetime | None, *, now: datetime) -> str:
    if value is None:
        return "-"
    return _seconds_label(_age_seconds(value, now=now))


def _age_seconds(value: datetime | None, *, now: datetime) -> int:
    if value is None:
        return 0
    return max(
        int((coerce_utc_datetime(now) - coerce_utc_datetime(value)).total_seconds()),
        0,
    )


def _seconds_label(value: float | int | None) -> str:
    if value is None:
        return "-"
    seconds = max(float(value), 0.0)
    if seconds < 1:
        return f"{int(seconds * 1000)}ms"
    if seconds < 60:
        formatted = f"{seconds:.2f}".rstrip("0").rstrip(".")
        return f"{formatted}s"
    minutes, remaining = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m {remaining}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def _datetime_label(value: datetime | None) -> str:
    return format_datetime_utc(value) if value is not None else "-"


def _status_label(status: str) -> str:
    return {
        "created": "Created",
        "running": "Running",
        "succeeded": "Succeeded",
        "failed": "Failed",
    }.get(status, status)


def _stream_status_label(
    invocation: LlmInvocation,
    *,
    events: tuple[OperationsObservedEvent, ...],
    now: datetime,
) -> str:
    if invocation.status is LlmInvocationStatus.FAILED:
        return "Failed"
    if invocation.status is LlmInvocationStatus.SUCCEEDED:
        return "Completed"
    delta_seen = any(
        event.event_name in {
            "llm.stream_delta_observed",
            "orchestration.run.llm_text_delta",
        }
        for event in events
    )
    if invocation.status is LlmInvocationStatus.RUNNING:
        return "Streaming" if delta_seen else "Connecting"
    if invocation.started_at is not None and (now - invocation.started_at).total_seconds() < 5:
        return "Connecting"
    return "Streaming" if delta_seen else "No"


def _status_tone(status: str) -> str:
    return {
        "created": "neutral",
        "running": "info",
        "succeeded": "success",
        "failed": "danger",
    }.get(status, "neutral")


def _event_tone(event: OperationsObservedEvent) -> str:
    if event.level == "error":
        return "danger"
    if event.level == "warning":
        return "warning"
    if event.status in {"succeeded", "completed", "ready"}:
        return "success"
    if event.status in {"running", "started"}:
        return "info"
    return "neutral"


def _response_item_tone(kind: str) -> str:
    if kind == "tool_call":
        return "info"
    if kind == "provider_external_item":
        return "warning"
    if kind == "assistant_message":
        return "success"
    return "neutral"


def _response_event_tone(event_type: str) -> str:
    if event_type == "failed":
        return "danger"
    if event_type in {"tool_argument_delta", "item_started", "item_completed"}:
        return "info"
    if event_type == "completed":
        return "success"
    return "neutral"


def _enum_value(value: Any) -> str:
    raw_value = getattr(value, "value", value)
    text = str(raw_value or "").strip()
    return text or "-"


def _provider_event_type(event: Any) -> str:
    provider_payload = getattr(event, "provider_payload", None)
    if isinstance(provider_payload, dict):
        event_type = provider_payload.get("type") or provider_payload.get(
            "provider_event_type",
        )
        if event_type is not None:
            return str(event_type)
    delta_payload = getattr(event, "delta_payload", None)
    if isinstance(delta_payload, dict):
        event_type = delta_payload.get("provider_event_type")
        if event_type is not None:
            return str(event_type)
    return "-"


def _chart_tone(index: int) -> str:
    return ("info", "success", "warning", "danger", "neutral")[index % 5]


def _error_family(error_code: str) -> str:
    text = error_code.lower()
    if any(token in text for token in ("rate", "quota", "429")):
        return "rate_limit"
    if any(token in text for token in ("auth", "access", "credential", "401", "403")):
        return "auth"
    if "timeout" in text:
        return "timeout"
    if any(token in text for token in ("context", "token", "length")):
        return "context_length"
    if any(token in text for token in ("unavailable", "connection", "provider", "503")):
        return "provider_down"
    if any(token in text for token in ("bad_request", "validation", "400")):
        return "bad_request"
    return "adapter_error"


def _retryable_error(category: str, error_code: str) -> bool:
    return category in {"rate_limit", "timeout", "provider_down"} or any(
        token in error_code.lower() for token in ("retry", "temporarily")
    )


def _request_payload(invocation: LlmInvocation) -> dict[str, Any]:
    return _sanitize_payload(
        {
            "llm_id": invocation.llm_id,
            "messages": [
                message.to_payload() if hasattr(message, "to_payload") else message
                for message in invocation.messages
            ],
            "tool_schemas": [
                schema.to_payload() if hasattr(schema, "to_payload") else schema
                for schema in invocation.tool_schemas
            ],
            "response_format": invocation.response_format,
            "overrides": invocation.request_overrides,
            "request_metadata": invocation.request_metadata,
            "provider_request_payload_preview": dict(
                invocation.provider_request_payload_preview,
            ),
        },
    )


def _result_payload(invocation: LlmInvocation) -> dict[str, Any] | None:
    if invocation.result is None:
        return None
    return _sanitize_payload(invocation.result.to_payload())


def _result_summary(invocation: LlmInvocation) -> str:
    if invocation.result is None:
        return ""
    if invocation.result.text:
        return _truncate(invocation.result.text, 240)
    if invocation.result.tool_calls:
        return f"{len(invocation.result.tool_calls)} tool calls"
    if invocation.result.structured_output is not None:
        return _json_preview(invocation.result.structured_output)
    if invocation.result.finish_reason:
        return invocation.result.finish_reason
    return ""


def _sanitize_payload(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return _truncate(value, 240)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _truncate(value, 512)
    if isinstance(value, dict):
        return {
            str(key): _sanitize_payload(item, depth=depth + 1)
            for key, item in list(value.items())[:40]
            if isinstance(key, str)
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize_payload(item, depth=depth + 1) for item in list(value)[:40]]
    return _truncate(value, 240)


def _json_preview(value: Any) -> str:
    try:
        return _truncate(
            json.dumps(_sanitize_payload(value), ensure_ascii=False, sort_keys=True),
            240,
        )
    except TypeError:
        return _truncate(value, 240)


def _truncate(value: Any, limit: int = 160) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _invocation_search_text(
    invocation: LlmInvocation,
    profile: LlmProfile | None,
) -> str:
    parts = [
        invocation.id,
        invocation.llm_id,
        invocation.status.value,
        profile.provider.value if profile is not None else "",
        profile.model_name if profile is not None else "",
        invocation.error.code if invocation.error is not None else "",
        invocation.error.message if invocation.error is not None else "",
    ]
    return " ".join(parts)


def _dedupe_invocations(
    invocations: tuple[LlmInvocation, ...],
) -> tuple[LlmInvocation, ...]:
    seen: set[str] = set()
    result: list[LlmInvocation] = []
    for invocation in invocations:
        if invocation.id in seen:
            continue
        seen.add(invocation.id)
        result.append(invocation)
    return tuple(result[:80])


def _columns(*pairs: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(OperationsTableColumnModel(key=key, label=label) for key, label in pairs)


def _text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def _text_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    items: list[str] = []
    for item in value:
        text = _text(item)
        if text is not None:
            items.append(text)
    return tuple(items)


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return False


def _float(value: Any) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0
