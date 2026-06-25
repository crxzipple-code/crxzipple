from __future__ import annotations

from typing import Any


def list_live_topics(
    events_service: Any | None,
    *,
    topic_prefix: str,
) -> tuple[str, ...]:
    if events_service is None:
        return ()
    try:
        topics = tuple(
            topic.strip()
            for topic in events_service.list_event_topics()
            if isinstance(topic, str) and topic.strip()
        )
    except Exception:
        return ()
    if topic_prefix:
        topics = tuple(topic for topic in topics if topic.startswith(topic_prefix))
    return tuple(sorted(dict.fromkeys(topics)))


def prioritized_topics(
    *,
    live_topics: tuple[str, ...],
    source_topics: set[str],
    limit: int,
) -> tuple[str, ...]:
    live_topic_set = set(live_topics)
    ordered: list[str] = []

    def add(topic: str) -> None:
        if topic in live_topic_set and topic not in ordered:
            ordered.append(topic)

    for topic in sorted(source_topics):
        add(topic)
    for prefix in (
        "events.named.orchestration.",
        "events.named.tool.",
        "events.named.llm.",
        "orchestration.",
        "tool.",
        "llm.",
        "turn.",
        "delivery.",
    ):
        for topic in live_topics:
            if topic.startswith(prefix):
                add(topic)
    for topic in live_topics:
        add(topic)
    return tuple(ordered[: max(1, limit)])


def safe_snapshot(events_service: Any | None, topic: str) -> str | None:
    if events_service is None:
        return None
    try:
        return events_service.snapshot_event_topic(topic)
    except Exception:
        return None
