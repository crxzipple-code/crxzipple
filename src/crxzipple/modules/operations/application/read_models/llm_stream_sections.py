from __future__ import annotations

from datetime import datetime

from crxzipple.modules.llm.domain import LlmInvocation, LlmInvocationStatus, LlmProfile
from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.llm_invocation_facts import (
    age_seconds,
    seconds_label,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_streaming import (
    profile_supports_streaming,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
    OperationsKeyValueSectionModel,
)

LONG_RUNNING_SECONDS = 120


def stream_health_section(
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
            age_seconds(invocation.started_at or invocation.created_at, now=now)
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
                value=seconds_label(longest_active),
                tone="warning" if longest_active >= LONG_RUNNING_SECONDS else "neutral",
            ),
            OperationsKeyValueItemModel(
                label="Stream-capable Profiles",
                value=str(sum(1 for profile in profiles if profile_supports_streaming(profile))),
                tone="neutral",
            ),
        ),
    )
