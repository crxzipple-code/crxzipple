from __future__ import annotations

from dataclasses import dataclass
from threading import Event as ThreadEvent
from crxzipple.modules.events.application.ports import (
    BusEvent,
    EventHandler,
    EventReadPort,
    EventPublisherPort,
    EventSubscriberPort,
    EventSubscriptionCursorPort,
    EventWaitPort,
)
from crxzipple.modules.events.domain import (
    EventCursor,
    EventSelector,
    EventSubscriptionCursor,
    EventTopicRecord,
    EventTopicWatch,
)


@dataclass(slots=True)
class EventsApplicationService:
    backend: (
        EventPublisherPort
        & EventSubscriberPort
        & EventWaitPort
        & EventReadPort
        & EventSubscriptionCursorPort
    )

    def publish(self, event: BusEvent) -> None:
        self.backend.publish(event)

    def publish_many(self, events: tuple[BusEvent, ...]) -> None:
        if not events:
            return
        self.backend.publish_many(events)

    def subscribe(
        self,
        selector: EventSelector,
        handler: EventHandler,
    ) -> None:
        self.backend.subscribe(selector, handler)

    def list_event_topics(self) -> tuple[str, ...]:
        return self.backend.list_event_topics()

    def snapshot_event_topic(self, topic: str) -> EventCursor:
        return self.backend.snapshot_event_topic(topic)

    def wait_for_event_topic(
        self,
        topic: str,
        *,
        after_cursor: EventCursor | None = None,
        timeout_seconds: float,
        stop_event: ThreadEvent | None = None,
    ) -> bool:
        return self.backend.wait_for_event_topic(
            topic,
            after_cursor=after_cursor,
            timeout_seconds=timeout_seconds,
            stop_event=stop_event,
        )

    def wait_for_event_topics(
        self,
        watches: tuple[EventTopicWatch, ...],
        *,
        timeout_seconds: float,
        stop_event: ThreadEvent | None = None,
    ) -> EventTopicWatch | None:
        return self.backend.wait_for_event_topics(
            watches,
            timeout_seconds=timeout_seconds,
            stop_event=stop_event,
        )

    def read_event_topic(
        self,
        topic: str,
        *,
        after_cursor: EventCursor | None = None,
        limit: int = 100,
    ) -> tuple[EventTopicRecord, ...]:
        return self.backend.read_event_topic(
            topic,
            after_cursor=after_cursor,
            limit=limit,
        )

    def read_recent_event_topic(
        self,
        topic: str,
        *,
        limit: int = 100,
    ) -> tuple[EventTopicRecord, ...]:
        return self.backend.read_recent_event_topic(topic, limit=limit)

    def get_subscription_cursor(
        self,
        subscription_id: str,
        *,
        source_topic: str | None = None,
    ) -> EventSubscriptionCursor | None:
        return self.backend.get_subscription_cursor(
            subscription_id,
            source_topic=source_topic,
        )

    def list_subscription_cursors(
        self,
        *,
        source_topic: str | None = None,
    ) -> tuple[EventSubscriptionCursor, ...]:
        return self.backend.list_subscription_cursors(source_topic=source_topic)

    def set_subscription_cursor(
        self,
        subscription_id: str,
        *,
        source_topic: str,
        cursor: EventCursor,
    ) -> EventSubscriptionCursor:
        return self.backend.set_subscription_cursor(
            subscription_id,
            source_topic=source_topic,
            cursor=cursor,
        )
