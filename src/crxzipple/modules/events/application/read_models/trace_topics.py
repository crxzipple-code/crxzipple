from __future__ import annotations

from crxzipple.modules.events.application import EventsApplicationService
from crxzipple.shared import EventDefinitionRegistry
from crxzipple.shared.domain.events import NAMED_EVENT_TOPIC_PREFIX, named_event_topic


def trace_source_topics(
    *,
    events_service: EventsApplicationService,
    registry: EventDefinitionRegistry,
) -> tuple[str, ...]:
    topics: set[str] = set()
    for definition in registry.list_definitions():
        definition_topics = definition.topics or (named_event_topic(definition.event_name),)
        for topic in definition_topics:
            normalized = _normalized_trace_source_topic(topic, require_named=True)
            if normalized is not None:
                topics.add(normalized)
    for topic in events_service.list_event_topics():
        normalized = _normalized_trace_source_topic(topic, require_named=False)
        if normalized is not None:
            topics.add(normalized)
    return tuple(sorted(topics))


def per_topic_trace_limit(*, limit: int, focus_id: str) -> int:
    if focus_id:
        return min(max(limit // 2, 50), 100)
    return min(max(limit, 50), 200)


def _normalized_trace_source_topic(
    topic: str,
    *,
    require_named: bool,
) -> str | None:
    if not isinstance(topic, str):
        return None
    normalized = topic.strip()
    if not normalized:
        return None
    if "{" in normalized or "}" in normalized:
        return None
    if normalized.startswith("event_relay.") or normalized.startswith("channel.observe."):
        return None
    if normalized == NAMED_EVENT_TOPIC_PREFIX or normalized.startswith(
        f"{NAMED_EVENT_TOPIC_PREFIX}.",
    ):
        return normalized
    if not require_named:
        return normalized
    return None
