from __future__ import annotations

from datetime import datetime

from crxzipple.modules.llm.domain import LlmInvocation, LlmProfile
from crxzipple.modules.operations.application.read_models.llm_invocation_facts import (
    age_seconds,
    seconds_label,
)
from crxzipple.modules.operations.application.read_models.llm_runtime_metrics import (
    LLM_LIMITER_ACTIVE,
    LLM_LIMITER_WAIT_SECONDS,
    LLM_LIMITER_WAITERS,
    combined_timing,
    metric_values_by_label,
    sum_metric_values,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
    OperationsKeyValueSectionModel,
)

LONG_RUNNING_SECONDS = 120


def rate_limiter_section(
    profiles: list[LlmProfile],
    *,
    runtime_snapshot: dict[str, object],
) -> OperationsKeyValueSectionModel:
    active = sum_metric_values(
        runtime_snapshot,
        section="gauges",
        name=LLM_LIMITER_ACTIVE,
    )
    waiters = sum_metric_values(
        runtime_snapshot,
        section="gauges",
        name=LLM_LIMITER_WAITERS,
    )
    timing = combined_timing(runtime_snapshot, LLM_LIMITER_WAIT_SECONDS)
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
                value=seconds_label(timing["avg_seconds"]),
                tone="warning" if timing["avg_seconds"] > 0 else "success",
            ),
            OperationsKeyValueItemModel(
                label="Max Wait",
                value=seconds_label(timing["max_seconds"]),
                tone="warning" if timing["max_seconds"] > 0 else "success",
            ),
        ),
    )


def execution_blocking_risk_section(
    profiles: list[LlmProfile],
    *,
    active_invocations: list[LlmInvocation],
    runtime_snapshot: dict[str, object],
    now: datetime,
) -> OperationsKeyValueSectionModel:
    waiters = sum_metric_values(
        runtime_snapshot,
        section="gauges",
        name=LLM_LIMITER_WAITERS,
    )
    active_by_key = metric_values_by_label(
        runtime_snapshot,
        section="gauges",
        name=LLM_LIMITER_ACTIVE,
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
            age_seconds(invocation.started_at or invocation.created_at, now=now)
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
                value=seconds_label(oldest_running),
                tone="warning" if oldest_running >= LONG_RUNNING_SECONDS else "neutral",
            ),
        ),
    )
