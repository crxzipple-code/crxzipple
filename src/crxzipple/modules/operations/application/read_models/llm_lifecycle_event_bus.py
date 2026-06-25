from __future__ import annotations

from typing import Any, Callable

from crxzipple.modules.operations.application.observation_event_projection import (
    observed_event_from_record,
)
from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.shared.time import coerce_utc_datetime

MAX_RECENT_LLM_EVENTS = 320
_MAX_LLM_EVENT_TOPICS = 240
_RECENT_LLM_TOPIC_LIMIT = 100
_LLM_DIRECT_EVENT_TOPICS = (
    "events.named.llm.profile_registered",
    "events.named.llm.profile_updated",
    "events.named.llm.profile_warmup_succeeded",
    "events.named.llm.profile_warmup_skipped",
    "events.named.llm.profile_warmup_failed",
    "events.named.llm.invocation_started",
    "events.named.llm.invocation_provider_request_prepared",
    "events.named.llm.invocation_succeeded",
    "events.named.llm.invocation_failed",
    "events.named.llm.stream_delta_observed",
    "events.named.orchestration.run.llm_text_delta",
    "llm.profile_registered",
    "llm.profile_updated",
    "llm.profile_warmup_succeeded",
    "llm.profile_warmup_skipped",
    "llm.profile_warmup_failed",
    "llm.invocation_started",
    "llm.invocation_provider_request_prepared",
    "llm.invocation_succeeded",
    "llm.invocation_failed",
    "llm.stream_delta_observed",
    "orchestration.run.llm_text_delta",
)
_LLM_RESOLVER_EVENT_TOPICS = (
    "events.named.orchestration.llm_resolved",
    "orchestration.llm_resolved",
)


def recent_llm_events_from_bus(
    events_service: Any | None,
    *,
    definition_registry: Any | None,
    limit: int,
) -> tuple[OperationsObservedEvent, ...]:
    return recent_observed_events_from_bus(
        events_service,
        definition_registry=definition_registry,
        seed_topics=_LLM_DIRECT_EVENT_TOPICS,
        topic_filter=is_llm_event_topic,
        event_filter=is_llm_observed_event,
        limit=limit,
    )


def recent_resolver_events_from_bus(
    events_service: Any | None,
    *,
    definition_registry: Any | None,
    limit: int,
) -> tuple[OperationsObservedEvent, ...]:
    return recent_observed_events_from_bus(
        events_service,
        definition_registry=definition_registry,
        seed_topics=_LLM_RESOLVER_EVENT_TOPICS,
        topic_filter=is_resolver_event_topic,
        event_filter=is_resolver_observed_event,
        limit=limit,
    )


def recent_observed_events_from_bus(
    events_service: Any | None,
    *,
    definition_registry: Any | None,
    seed_topics: tuple[str, ...] = (),
    topic_filter: Callable[[str], bool],
    event_filter: Callable[[OperationsObservedEvent], bool],
    limit: int,
) -> tuple[OperationsObservedEvent, ...]:
    if events_service is None:
        return ()
    topics = dedupe_topic_names(
        (
            *seed_topics,
            *(
                topic
                for topic in safe_list_event_topics(events_service)
                if topic_filter(topic)
            ),
        ),
    )[:_MAX_LLM_EVENT_TOPICS]
    read_recent = getattr(events_service, "read_recent_event_topic", None)
    if not callable(read_recent):
        return ()
    events: list[OperationsObservedEvent] = []
    topic_limit = min(max(_RECENT_LLM_TOPIC_LIMIT, int(limit)), MAX_RECENT_LLM_EVENTS)
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
    return tuple(events[:MAX_RECENT_LLM_EVENTS])


def safe_list_event_topics(events_service: Any) -> tuple[str, ...]:
    list_topics = getattr(events_service, "list_event_topics", None)
    if not callable(list_topics):
        return ()
    try:
        return tuple(str(topic) for topic in list_topics() or () if str(topic))
    except Exception:
        return ()


def dedupe_topic_names(topics: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for topic in topics:
        normalized = topic.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return tuple(result)


def is_llm_event_topic(topic: str) -> bool:
    normalized = topic.strip().lower()
    return (
        normalized.startswith("llm.")
        or normalized.startswith("events.named.llm.")
        or normalized == "orchestration.run.llm_text_delta"
        or normalized == "events.named.orchestration.run.llm_text_delta"
    )


def is_llm_observed_event(event: OperationsObservedEvent) -> bool:
    owner = event.owner.strip().lower()
    module = event.module.strip().lower()
    event_name = event.event_name.strip().lower()
    return (
        owner == "llm"
        or module == "llm"
        or event_name.startswith("llm.")
        or event_name == "orchestration.run.llm_text_delta"
    )


def is_resolver_event_topic(topic: str) -> bool:
    normalized = topic.strip().lower()
    return (
        normalized == "orchestration.llm_resolved"
        or normalized == "events.named.orchestration.llm_resolved"
    )


def is_resolver_observed_event(event: OperationsObservedEvent) -> bool:
    return event.event_name.strip().lower() == "orchestration.llm_resolved"
