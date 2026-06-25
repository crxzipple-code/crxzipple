from __future__ import annotations

from typing import Any

from crxzipple.modules.llm.domain import LlmInvocation
from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.ports_llm_agent import (
    OperationsLlmQueryPort,
)


def events_by_invocation(
    events: tuple[OperationsObservedEvent, ...],
) -> dict[str, tuple[OperationsObservedEvent, ...]]:
    grouped: dict[str, list[OperationsObservedEvent]] = {}
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
            grouped.setdefault(invocation_id, []).append(event)
    return {
        key: tuple(sorted(items, key=lambda event: event.occurred_at, reverse=True))
        for key, items in grouped.items()
    }


def response_events_by_invocation(
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


def response_event_retention_policy(
    llm_service: OperationsLlmQueryPort,
) -> dict[str, object]:
    read_policy = getattr(llm_service, "response_event_retention_policy", None)
    if not callable(read_policy):
        return {}
    try:
        policy = read_policy()
    except Exception:
        return {}
    to_payload = getattr(policy, "to_payload", None)
    if callable(to_payload):
        try:
            payload = to_payload()
            return dict(payload) if isinstance(payload, dict) else {}
        except Exception:
            return {}
    if isinstance(policy, dict):
        return dict(policy)
    return {}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
