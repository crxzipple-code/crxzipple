from __future__ import annotations

from typing import Any

from crxzipple.modules.channels.domain import channel_dead_letter_topic
from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.channels_event_records import (
    channel_event_from_observed_event,
    channel_event_from_record,
    with_connection_binding,
)
from crxzipple.modules.operations.application.read_models.channels_connection_helpers import (
    connection_binding_by_conversation,
    connection_event_topics,
)
from crxzipple.modules.operations.application.read_models.channels_event_helpers import (
    MAX_EVENT_TOPICS,
    MAX_RECENT_EVENTS,
    RECENT_TOPIC_LIMIT,
    dedupe_events,
)
from crxzipple.modules.operations.application.read_models.channels_formatting import (
    text,
)
from crxzipple.modules.operations.application.read_models.channels_models import (
    ChannelEventRecord,
)
from crxzipple.modules.operations.application.read_models.channels_safe_access import (
    safe_list_event_topics,
)
from crxzipple.modules.operations.application.read_models.channels_topic_helpers import (
    channel_from_topic,
)


def channel_types(
    *,
    profiles: tuple[Any, ...],
    runtimes: tuple[Any, ...],
    account_bindings: tuple[Any, ...],
    connection_bindings: tuple[Any, ...],
    interactions: tuple[Any, ...],
    events_service: Any | None,
) -> tuple[str, ...]:
    values = {
        text(getattr(item, "channel_type", None), "")
        for item in (
            *profiles,
            *runtimes,
            *account_bindings,
            *connection_bindings,
            *interactions,
        )
    }
    if events_service is not None:
        values.update(
            channel_from_topic(topic) or ""
            for topic in safe_list_event_topics(events_service)
            if topic.startswith("channel.")
        )
    values.update({"web", "lark", "webhook"})
    return tuple(sorted(value for value in values if value))


def dead_letter_events(
    events_service: Any | None,
    *,
    channel_types: tuple[str, ...],
    runtimes: tuple[Any, ...],
    definition_registry: Any | None,
) -> tuple[ChannelEventRecord, ...]:
    if events_service is None:
        return ()
    topics = {
        topic
        for topic in safe_list_event_topics(events_service)
        if topic.startswith("channel.dead_letter.")
    }
    for channel_type in channel_types:
        topics.add(channel_dead_letter_topic(channel_type))
    for runtime in runtimes:
        channel_type = text(getattr(runtime, "channel_type", None), "")
        runtime_id = text(getattr(runtime, "runtime_id", None), "")
        if channel_type and runtime_id:
            topics.add(channel_dead_letter_topic(channel_type, runtime_id=runtime_id))
    return read_event_records(
        events_service,
        tuple(sorted(topics)),
        definition_registry=definition_registry,
        per_topic_limit=80,
    )


def recent_channel_events(
    events_service: Any | None,
    *,
    connection_bindings: tuple[Any, ...],
    definition_registry: Any | None,
) -> tuple[ChannelEventRecord, ...]:
    if events_service is None:
        return ()
    live_topics = safe_list_event_topics(events_service)
    topic_set = {
        topic
        for topic in live_topics
        if topic.startswith("channel.")
    }
    topic_set.update(
        topic
        for topic in connection_event_topics(connection_bindings)
        if topic in live_topics
    )
    topics = tuple(sorted(topic_set))[:MAX_EVENT_TOPICS]
    events = read_event_records(
        events_service,
        topics,
        definition_registry=definition_registry,
        per_topic_limit=RECENT_TOPIC_LIMIT,
    )
    binding_by_conversation = connection_binding_by_conversation(connection_bindings)
    return tuple(
        with_connection_binding(event, binding_by_conversation=binding_by_conversation)
        for event in events
    )


def recent_channel_events_from_observation(
    operations_observation: Any | None,
    *,
    connection_bindings: tuple[Any, ...],
) -> tuple[ChannelEventRecord, ...]:
    get_module_observation = getattr(operations_observation, "get_module_observation", None)
    if not callable(get_module_observation):
        return ()
    try:
        observation = get_module_observation("channels")
    except Exception:
        return ()
    binding_by_conversation = connection_binding_by_conversation(connection_bindings)
    events = tuple(
        with_connection_binding(
            channel_event_from_observed_event(observed),
            binding_by_conversation=binding_by_conversation,
        )
        for observed in tuple(getattr(observation, "recent_events", ()) or ())
        if isinstance(observed, OperationsObservedEvent)
    )
    return dedupe_events(events)[:MAX_RECENT_EVENTS]


def read_event_records(
    events_service: Any,
    topics: tuple[str, ...],
    *,
    definition_registry: Any | None,
    per_topic_limit: int,
) -> tuple[ChannelEventRecord, ...]:
    records: list[ChannelEventRecord] = []
    for topic in topics:
        read_recent = getattr(events_service, "read_recent_event_topic", None)
        if not callable(read_recent):
            continue
        try:
            topic_records = read_recent(topic, limit=per_topic_limit)
        except Exception:
            continue
        for record in tuple(topic_records or ()):
            records.append(
                channel_event_from_record(
                    record,
                    definition_registry=definition_registry,
                )
            )
    records.sort(key=lambda item: item.occurred_at, reverse=True)
    return tuple(records[:MAX_RECENT_EVENTS])
