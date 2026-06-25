from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.llm.domain import LlmInvocationStatus
from crxzipple.modules.operations.application.read_models.llm_invocation_facts import (
    token_total as _token_total,
)
from crxzipple.modules.operations.application.read_models.llm_overview_actions import (
    llm_actions as _actions,
)
from crxzipple.modules.operations.application.read_models.llm_overview_sections import (
    llm_health as _health,
    llm_health_delta as _health_delta,
    llm_health_label as _health_label,
    llm_health_tone as _health_tone,
)
from crxzipple.modules.operations.application.read_models.llm_overview_rows import (
    max_context_label as _max_context_label,
    profile_limit_rows as _profile_limit_rows,
    profile_rows as _profile_rows,
    queue_rows as _queue_rows,
)
from crxzipple.modules.operations.application.read_models.llm_provider_readiness import (
    blocked_profiles as _blocked_profiles,
)
from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsModuleOverview,
)
from crxzipple.modules.operations.application.read_models.ports_llm_agent import (
    OperationsLlmQueryPort,
)
from crxzipple.shared.time import format_datetime_utc

_INVOCATION_OVERVIEW_LIMIT = 240


def llm_operations_overview(
    *,
    llm_service: OperationsLlmQueryPort,
    access_service: Any | None = None,
) -> OperationsModuleOverview:
    now = datetime.now(timezone.utc)
    profiles = llm_service.list_profiles()
    invocations = llm_service.list_invocations(
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
            access_service=access_service,
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
