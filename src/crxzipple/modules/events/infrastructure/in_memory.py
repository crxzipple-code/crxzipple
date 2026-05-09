from __future__ import annotations

from collections import defaultdict
from threading import Condition, Event as ThreadEvent
import time

from crxzipple.core.logger import get_logger
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
logger = get_logger(__name__)


class InMemoryEventsBackend(
    EventPublisherPort,
    EventSubscriberPort,
    EventWaitPort,
    EventReadPort,
    EventSubscriptionCursorPort,
):
    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._topic_cursors: dict[str, int] = defaultdict(int)
        self._topic_records: dict[str, list[EventTopicRecord]] = defaultdict(list)
        self._topic_dedupe: dict[str, dict[str, str]] = defaultdict(dict)
        self._topic_conditions: dict[str, Condition] = defaultdict(Condition)
        self._any_topic_condition = Condition()
        self._subscription_cursors: dict[str, EventSubscriptionCursor] = {}
        self.published_events: list[BusEvent] = []

    def publish(self, event: BusEvent) -> None:
        self.publish_many((event,))

    def publish_many(self, events: tuple[BusEvent, ...]) -> None:
        if not events:
            return
        handled_events: list[BusEvent] = []
        self.published_events.extend(events)
        for event in events:
            topic = event.topic
            assert topic is not None
            topic_condition = self._topic_conditions[topic]
            with topic_condition:
                if (
                    event.dedupe_key is not None
                    and event.dedupe_key in self._topic_dedupe[topic]
                ):
                    continue
                self._topic_cursors[topic] += 1
                current_cursor = self._topic_cursors[topic]
                self._topic_records[topic].append(
                    EventTopicRecord(cursor=str(current_cursor), envelope=event),
                )
                if event.dedupe_key is not None:
                    self._topic_dedupe[topic][event.dedupe_key] = str(
                        current_cursor
                    )
                topic_condition.notify_all()
            handled_events.append(event)
        if handled_events:
            with self._any_topic_condition:
                self._any_topic_condition.notify_all()
        for event in handled_events:
            selector = event.selector
            logger.debug(
                "publishing event",
                extra={
                    "topic": event.topic,
                    "event_name": event.event_name,
                    "kind": event.kind,
                    "handler_count": len(self._handlers.get(selector.key, [])),
                },
            )
            for handler in self._handlers.get(selector.key, []):
                handler(event)

    def subscribe(
        self,
        selector: EventSelector,
        handler: EventHandler,
    ) -> None:
        self._handlers[selector.key].append(handler)
        logger.debug(
            "registered event topic handler",
            extra={
                "topic": selector.topic,
                "handler_count": len(self._handlers[selector.key]),
            },
        )

    def list_event_topics(self) -> tuple[str, ...]:
        topics = {
            *self._topic_cursors.keys(),
            *self._topic_records.keys(),
        }
        return tuple(
            sorted(
                topic
                for topic in topics
                if isinstance(topic, str) and topic.strip()
            ),
        )

    def snapshot_event_topic(self, topic: str) -> EventCursor:
        topic_condition = self._topic_conditions[topic]
        with topic_condition:
            return str(self._topic_cursors[topic])

    def read_recent_event_topic(
        self,
        topic: str,
        *,
        limit: int = 100,
    ) -> tuple[EventTopicRecord, ...]:
        if limit <= 0:
            return ()
        topic_condition = self._topic_conditions[topic]
        with topic_condition:
            return tuple(self._topic_records[topic][-limit:])

    def wait_for_event_topic(
        self,
        topic: str,
        *,
        after_cursor: EventCursor | None = None,
        timeout_seconds: float,
        stop_event: ThreadEvent | None = None,
    ) -> bool:
        cursor_value = self._parse_cursor(after_cursor)
        remaining = max(float(timeout_seconds), 0.0)
        deadline = time.monotonic() + remaining
        topic_condition = self._topic_conditions[topic]
        with topic_condition:
            if self._topic_cursors[topic] > cursor_value:
                return True
            while True:
                if stop_event is not None and stop_event.is_set():
                    return False
                if remaining <= 0:
                    return self._topic_cursors[topic] > cursor_value
                topic_condition.wait(timeout=min(remaining, 0.1))
                if self._topic_cursors[topic] > cursor_value:
                    return True
                remaining = deadline - time.monotonic()

    def wait_for_event_topics(
        self,
        watches: tuple[EventTopicWatch, ...],
        *,
        timeout_seconds: float,
        stop_event: ThreadEvent | None = None,
    ) -> EventTopicWatch | None:
        normalized = self._normalize_watches(watches)
        if not normalized:
            return None
        remaining = max(float(timeout_seconds), 0.0)
        deadline = time.monotonic() + remaining
        with self._any_topic_condition:
            triggered = self._first_triggered_watch(normalized)
            if triggered is not None:
                return triggered
            while True:
                if stop_event is not None and stop_event.is_set():
                    return None
                if remaining <= 0:
                    return self._first_triggered_watch(normalized)
                self._any_topic_condition.wait(timeout=min(remaining, 0.1))
                triggered = self._first_triggered_watch(normalized)
                if triggered is not None:
                    return triggered
                remaining = deadline - time.monotonic()

    def read_event_topic(
        self,
        topic: str,
        *,
        after_cursor: EventCursor | None = None,
        limit: int = 100,
    ) -> tuple[EventTopicRecord, ...]:
        if limit <= 0:
            return ()
        cursor_value = self._parse_cursor(after_cursor)
        topic_condition = self._topic_conditions[topic]
        with topic_condition:
            records = tuple(
                record
                for record in self._topic_records[topic]
                if self._parse_cursor(record.cursor) > cursor_value
            )
        return records[:limit]

    def get_subscription_cursor(
        self,
        subscription_id: str,
        *,
        source_topic: str | None = None,
    ) -> EventSubscriptionCursor | None:
        normalized_id = subscription_id.strip()
        if not normalized_id:
            return None
        state = self._subscription_cursors.get(normalized_id)
        if state is None:
            return None
        if source_topic is not None and state.source_topic != source_topic.strip():
            return None
        return state

    def list_subscription_cursors(
        self,
        *,
        source_topic: str | None = None,
    ) -> tuple[EventSubscriptionCursor, ...]:
        normalized_source = source_topic.strip() if source_topic is not None else None
        states = tuple(
            state
            for state in self._subscription_cursors.values()
            if normalized_source is None or state.source_topic == normalized_source
        )
        return tuple(
            sorted(
                states,
                key=lambda state: (state.source_topic, state.subscription_id),
            ),
        )

    def set_subscription_cursor(
        self,
        subscription_id: str,
        *,
        source_topic: str,
        cursor: EventCursor,
    ) -> EventSubscriptionCursor:
        state = EventSubscriptionCursor(
            subscription_id=subscription_id.strip(),
            source_topic=source_topic.strip(),
            cursor=str(cursor).strip(),
        )
        self._subscription_cursors[state.subscription_id] = state
        return state

    @staticmethod
    def _parse_cursor(cursor: EventCursor | None) -> int:
        if cursor is None:
            return 0
        try:
            return max(int(cursor), 0)
        except (TypeError, ValueError):
            return 0

    @classmethod
    def _normalize_watches(
        cls,
        watches: tuple[EventTopicWatch, ...],
    ) -> tuple[EventTopicWatch, ...]:
        return tuple(
            EventTopicWatch(
                topic=watch.topic.strip(),
                after_cursor=watch.after_cursor,
            )
            for watch in watches
            if isinstance(watch.topic, str) and watch.topic.strip()
        )

    def _first_triggered_watch(
        self,
        watches: tuple[EventTopicWatch, ...],
    ) -> EventTopicWatch | None:
        for watch in watches:
            if self._topic_cursors[watch.topic] > self._parse_cursor(watch.after_cursor):
                return watch
        return None
