from __future__ import annotations

from crxzipple.modules.events.domain import EventCursor, EventTopicWatch
from crxzipple.modules.operations.application.observer_subscriptions import (
    OperationsObserverSubscription,
)
from crxzipple.modules.operations.application.ports import OperationsEventStreamPort


class OperationsObserverCursorState:
    """Caches durable subscription cursors for one observer runtime process."""

    def __init__(
        self,
        *,
        events_service: OperationsEventStreamPort,
        start_at_tail_when_no_cursor: bool = False,
    ) -> None:
        self._events_service = events_service
        self._start_at_tail_when_no_cursor = bool(start_at_tail_when_no_cursor)
        self._subscription_cursors: dict[tuple[str, str], EventCursor | None] = {}

    def cursor(self, subscription: OperationsObserverSubscription) -> EventCursor | None:
        key = (subscription.subscription_id, subscription.source_topic)
        if key not in self._subscription_cursors:
            state = self._events_service.get_subscription_cursor(
                subscription.subscription_id,
                source_topic=subscription.source_topic,
            )
            if state is not None:
                self._subscription_cursors[key] = state.cursor
            elif self._start_at_tail_when_no_cursor:
                cursor = self._events_service.snapshot_event_topic(
                    subscription.source_topic,
                )
                self._events_service.set_subscription_cursor(
                    subscription.subscription_id,
                    source_topic=subscription.source_topic,
                    cursor=cursor,
                )
                self._subscription_cursors[key] = cursor
            else:
                self._subscription_cursors[key] = None
        return self._subscription_cursors[key]

    def set_cursor(
        self,
        subscription: OperationsObserverSubscription,
        cursor: EventCursor,
    ) -> None:
        self._subscription_cursors[
            (subscription.subscription_id, subscription.source_topic)
        ] = cursor

    def build_wait_watches(
        self,
        subscriptions: tuple[OperationsObserverSubscription, ...],
    ) -> tuple[EventTopicWatch, ...]:
        return tuple(
            EventTopicWatch(
                topic=subscription.source_topic,
                after_cursor=self.cursor(subscription),
            )
            for subscription in subscriptions
        )
