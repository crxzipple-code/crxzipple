from __future__ import annotations

from collections.abc import Callable
from threading import Event as ThreadEvent
from typing import Protocol

from crxzipple.modules.events.domain import (
    EventCursor,
    EventSelector,
    EventSubscriptionCursor,
    EventTopicRecord,
    EventTopicWatch,
)
from crxzipple.shared.domain.events import Event

BusEvent = Event
EventHandler = Callable[[Event], None]


class EventPublisherPort(Protocol):
    def publish(self, event: BusEvent) -> None:
        ...

    def publish_many(self, events: tuple[BusEvent, ...]) -> None:
        ...


class EventSubscriberPort(Protocol):
    def subscribe(
        self,
        selector: EventSelector,
        handler: EventHandler,
    ) -> None:
        ...


class EventWaitPort(Protocol):
    def list_event_topics(self) -> tuple[str, ...]:
        ...

    def snapshot_event_topic(self, topic: str) -> EventCursor:
        ...

    def wait_for_event_topic(
        self,
        topic: str,
        *,
        after_cursor: EventCursor | None = None,
        timeout_seconds: float,
        stop_event: ThreadEvent | None = None,
    ) -> bool:
        ...

    def wait_for_event_topics(
        self,
        watches: tuple[EventTopicWatch, ...],
        *,
        timeout_seconds: float,
        stop_event: ThreadEvent | None = None,
    ) -> EventTopicWatch | None:
        ...


class EventReadPort(Protocol):
    def read_recent_event_topic(
        self,
        topic: str,
        *,
        limit: int = 100,
    ) -> tuple[EventTopicRecord, ...]:
        ...

    def read_event_topic(
        self,
        topic: str,
        *,
        after_cursor: EventCursor | None = None,
        limit: int = 100,
    ) -> tuple[EventTopicRecord, ...]:
        ...


class EventSubscriptionCursorPort(Protocol):
    def list_subscription_cursors(
        self,
        *,
        source_topic: str | None = None,
    ) -> tuple[EventSubscriptionCursor, ...]:
        ...

    def get_subscription_cursor(
        self,
        subscription_id: str,
        *,
        source_topic: str | None = None,
    ) -> EventSubscriptionCursor | None:
        ...

    def set_subscription_cursor(
        self,
        subscription_id: str,
        *,
        source_topic: str,
        cursor: EventCursor,
    ) -> EventSubscriptionCursor:
        ...
