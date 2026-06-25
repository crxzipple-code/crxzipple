from __future__ import annotations

from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.shared.time import coerce_utc_datetime

DAEMON_DIRECT_EVENT_TOPICS = (
    "events.named.daemon.service.ensure_requested",
    "events.named.daemon.service.healthcheck_requested",
    "events.named.daemon.service.reconcile_requested",
    "events.named.daemon.service.stop_requested",
    "events.named.daemon.instance.started",
    "events.named.daemon.instance.ready",
    "events.named.daemon.instance.degraded",
    "events.named.daemon.instance.failed",
    "events.named.daemon.instance.stopped",
    "events.named.daemon.lease.acquired",
    "events.named.daemon.lease.heartbeated",
    "events.named.daemon.lease.released",
    "events.named.daemon.lease.expired",
    "events.named.process.session.started",
    "events.named.process.session.exited",
    "events.named.process.session.failed",
    "events.named.process.session.output_observed",
    "daemon.service.ensure_requested",
    "daemon.service.healthcheck_requested",
    "daemon.service.reconcile_requested",
    "daemon.service.stop_requested",
    "daemon.instance.started",
    "daemon.instance.ready",
    "daemon.instance.degraded",
    "daemon.instance.failed",
    "daemon.instance.stopped",
    "daemon.lease.acquired",
    "daemon.lease.heartbeated",
    "daemon.lease.released",
    "daemon.lease.expired",
    "process.session.started",
    "process.session.exited",
    "process.session.failed",
    "process.session.output_observed",
)


def daemon_event_topics(values: tuple[str, ...]) -> tuple[str, ...]:
    return dedupe_topic_names(
        (
            *DAEMON_DIRECT_EVENT_TOPICS,
            *(topic for topic in values if is_daemon_event_topic(topic)),
        ),
    )


def is_daemon_event_topic(topic: str) -> bool:
    normalized = topic.strip().lower()
    return (
        normalized.startswith("daemon.")
        or normalized.startswith("events.named.daemon.")
        or normalized.startswith("process.")
        or normalized.startswith("events.named.process.")
    )


def is_daemon_observed_event(event: OperationsObservedEvent) -> bool:
    owner = event.owner.strip().lower()
    module = event.module.strip().lower()
    event_name = event.event_name.strip().lower()
    return (
        owner in {"daemon", "process"}
        or module in {"daemon", "process"}
        or event_name.startswith("daemon.")
        or event_name.startswith("process.")
    )


def dedupe_daemon_events(
    events: tuple[OperationsObservedEvent, ...],
    *,
    limit: int,
) -> tuple[OperationsObservedEvent, ...]:
    result: list[OperationsObservedEvent] = []
    seen: set[tuple[str, str]] = set()
    for event in sorted(
        events,
        key=lambda item: coerce_utc_datetime(item.occurred_at),
        reverse=True,
    ):
        key = (event.topic, event.cursor or event.id)
        if key in seen:
            continue
        seen.add(key)
        result.append(event)
    return tuple(result[:limit])


def dedupe_topic_names(values: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return tuple(result)
