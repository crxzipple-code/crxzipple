from __future__ import annotations

from threading import Event as ThreadEvent
from typing import Protocol

from crxzipple.modules.events.domain import (
    EventCursor,
    EventSubscriptionCursor,
    EventTopicRecord,
    EventTopicWatch,
)


class ToolEventWaitPort(Protocol):
    def snapshot_event_topic(self, topic: str) -> EventCursor:
        ...

    def wait_for_event_topics(
        self,
        watches: tuple[EventTopicWatch, ...],
        *,
        timeout_seconds: float,
        stop_event: ThreadEvent | None = None,
    ) -> EventTopicWatch | None:
        ...


class ToolEventSubscriptionStreamPort(ToolEventWaitPort, Protocol):
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

    def read_event_topic(
        self,
        topic: str,
        *,
        after_cursor: EventCursor | None = None,
        limit: int = 100,
    ) -> tuple[EventTopicRecord, ...]:
        ...
