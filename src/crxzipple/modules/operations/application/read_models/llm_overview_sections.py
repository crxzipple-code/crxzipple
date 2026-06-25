from __future__ import annotations

from crxzipple.modules.llm.domain import LlmInvocation, LlmInvocationStatus, LlmProfile
from crxzipple.modules.operations.application.read_models.llm_invocation_facts import (
    duration_seconds,
    seconds_label,
    token_total,
)
from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
)
from crxzipple.modules.operations.application.read_models.presenters import (
    health_delta,
    health_label,
    health_tone,
)


def llm_health(
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


def llm_health_label(health: str) -> str:
    return health_label(health)


def llm_health_delta(health: str) -> str:
    return health_delta(health, healthy="LLM runtime state is queryable")


def llm_health_tone(health: str) -> str:
    return health_tone(health)


def page_metric_cards(
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
        for duration in (duration_seconds(invocation),)
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
            value=llm_health_label(health),
            delta=llm_health_delta(health),
            tone=llm_health_tone(health),
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
            value=str(token_total(invocations)),
            delta="reported by providers",
            tone="info" if token_total(invocations) else "neutral",
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
            value=seconds_label(average_latency),
            delta=f"{len(profiles)} configured profiles",
            tone="neutral",
        ),
    )
