from __future__ import annotations

from threading import Event as StopEvent
from typing import Protocol

from crxzipple.modules.events.domain import (
    EventCursor,
    EventSubscriptionCursor,
    EventTopicRecord,
    EventTopicWatch,
)
from crxzipple.shared.domain.events import Event


class OperationsEventPublishPort(Protocol):
    def publish(self, event: Event) -> None: ...


class OperationsEventStreamPort(OperationsEventPublishPort, Protocol):
    def list_event_topics(self) -> tuple[str, ...]: ...

    def snapshot_event_topic(self, topic: str) -> EventCursor: ...

    def read_recent_event_topic(
        self,
        topic: str,
        *,
        limit: int = 100,
    ) -> tuple[EventTopicRecord, ...]: ...

    def read_event_topic(
        self,
        topic: str,
        *,
        after_cursor: EventCursor | None = None,
        limit: int = 100,
    ) -> tuple[EventTopicRecord, ...]: ...

    def list_subscription_cursors(
        self,
        *,
        source_topic: str | None = None,
    ) -> tuple[EventSubscriptionCursor, ...]: ...

    def get_subscription_cursor(
        self,
        subscription_id: str,
        *,
        source_topic: str,
    ) -> EventSubscriptionCursor | None: ...

    def set_subscription_cursor(
        self,
        subscription_id: str,
        *,
        source_topic: str,
        cursor: EventCursor,
    ) -> None: ...

    def wait_for_event_topics(
        self,
        watches: tuple[EventTopicWatch, ...],
        *,
        timeout_seconds: float,
        stop_event: StopEvent | None = None,
    ) -> EventTopicWatch | None: ...
