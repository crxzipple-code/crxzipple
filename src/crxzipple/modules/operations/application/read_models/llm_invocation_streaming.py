from __future__ import annotations

from typing import Any

from crxzipple.modules.llm.domain import LlmInvocation, LlmInvocationStatus, LlmProfile
from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)


def streaming_invocations(
    invocations: list[LlmInvocation],
    *,
    profiles_by_id: dict[str, LlmProfile],
    observed_events: tuple[OperationsObservedEvent, ...],
) -> list[LlmInvocation]:
    streaming_ids = streaming_invocation_ids(observed_events)
    return [
        invocation
        for invocation in invocations
        if invocation.id in streaming_ids
        or (
            invocation.status is LlmInvocationStatus.RUNNING
            and profile_supports_streaming(profiles_by_id.get(invocation.llm_id))
        )
    ]


def streaming_invocation_ids(
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


def profile_supports_streaming(profile: LlmProfile | None) -> bool:
    if profile is None:
        return False
    return any(capability.value == "streaming" for capability in profile.capabilities)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return False
