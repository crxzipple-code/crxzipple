from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
import json
from threading import Event as ThreadEvent, Lock, Thread
import time
from typing import Any
from uuid import uuid4

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
from crxzipple.shared.domain.events import Event

logger = get_logger(__name__)


class RedisEventsBackend(
    EventPublisherPort,
    EventSubscriberPort,
    EventWaitPort,
    EventReadPort,
    EventSubscriptionCursorPort,
):
    def __init__(
        self,
        redis_url: str | None = None,
        *,
        client: Any | None = None,
        key_prefix: str = "crx:events",
        block_ms: int = 1000,
        dedupe_ttl_seconds: int = 3600,
    ) -> None:
        if client is None:
            if redis_url is None or not redis_url.strip():
                raise ValueError("redis_url is required when no Redis client is provided.")
            try:
                import redis  # type: ignore[import-not-found]
            except ModuleNotFoundError as exc:  # pragma: no cover - depends on local env
                raise RuntimeError(
                    "RedisEventsBackend requires the 'redis' package. "
                    "Install project dependencies or keep APP_EVENTS_BACKEND=file."
                ) from exc
            client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._client = client
        self._redis_url = redis_url.strip() if isinstance(redis_url, str) and redis_url.strip() else None
        self._key_prefix = key_prefix.strip() or "crx:events"
        self._block_ms = max(int(block_ms), 1)
        self._dedupe_ttl_seconds = max(int(dedupe_ttl_seconds), 1)
        self._publisher_id = uuid4().hex
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._listener_threads: dict[str, Thread] = {}
        self._listener_stop_events: dict[str, ThreadEvent] = {}
        self._listener_lock = Lock()
        self.published_events: list[BusEvent] = []

    def publish(self, event: BusEvent) -> None:
        self.publish_many((event,))

    def publish_many(self, events: tuple[BusEvent, ...]) -> None:
        if not events:
            return
        self.published_events.extend(events)
        publishable_events: list[BusEvent] = []
        for event in events:
            topic = event.topic
            assert topic is not None
            if event.dedupe_key is not None:
                dedupe_set = self._call_client(
                    "deduplicate topic event",
                    self._client.set,
                    self._dedupe_key(topic, event.dedupe_key),
                    event.id,
                    nx=True,
                    ex=self._dedupe_ttl_seconds,
                )
                if not dedupe_set:
                    continue
            publishable_events.append(event)
        cursors = self._publish_events_to_redis(publishable_events)
        for event, cursor in zip(publishable_events, cursors):
            selector = event.selector
            logger.debug(
                "publishing event through redis events backend",
                extra={
                    "topic": event.topic,
                    "event_name": event.event_name,
                    "kind": event.kind,
                    "cursor": cursor,
                    "handler_count": len(self._handlers.get(selector.key, [])),
                },
            )
            for handler in self._snapshot_handlers(selector):
                handler(event)

    def _publish_events_to_redis(self, events: list[BusEvent]) -> list[str]:
        if not events:
            return []
        pipeline_factory = getattr(self._client, "pipeline", None)
        if not callable(pipeline_factory):
            return [
                self._publish_event_to_redis(event)
                for event in events
            ]
        pipeline = pipeline_factory()
        for event in events:
            topic = event.topic
            assert topic is not None
            payload = {
                "publisher_id": self._publisher_id,
                "envelope": event.to_payload(),
            }
            pipeline.xadd(
                self._topic_stream_key(topic),
                {
                    "record": json.dumps(
                        payload,
                        ensure_ascii=True,
                        separators=(",", ":"),
                    ),
                },
            )
        return list(
            self._call_client(
                "publish events",
                pipeline.execute,
            ),
        )

    def _publish_event_to_redis(self, event: BusEvent) -> str:
        topic = event.topic
        assert topic is not None
        payload = {
            "publisher_id": self._publisher_id,
            "envelope": event.to_payload(),
        }
        return self._call_client(
            "publish event",
            self._client.xadd,
            self._topic_stream_key(topic),
            {"record": json.dumps(payload, ensure_ascii=True, separators=(",", ":"))},
        )

    def subscribe(
        self,
        selector: EventSelector,
        handler: EventHandler,
    ) -> None:
        self._handlers[selector.key].append(handler)
        logger.debug(
            "registered event topic handler on redis events backend",
            extra={
                "topic": selector.topic,
                "handler_count": len(self._handlers[selector.key]),
            },
        )
        self._ensure_topic_listener(
            selector.topic,
            start_cursor=self._snapshot_stream(self._topic_stream_key(selector.topic)),
        )

    def list_event_topics(self) -> tuple[str, ...]:
        prefix = f"{self._key_prefix}:topic:"
        keys = self._list_keys(f"{prefix}*")
        topics = []
        for key in keys:
            if not key.startswith(prefix):
                continue
            topic = key[len(prefix):].strip()
            if topic:
                topics.append(topic)
        return tuple(sorted(dict.fromkeys(topics)))

    def snapshot_event_topic(self, topic: str) -> EventCursor:
        return self._snapshot_stream(self._topic_stream_key(topic))

    def read_recent_event_topic(
        self,
        topic: str,
        *,
        limit: int = 100,
    ) -> tuple[EventTopicRecord, ...]:
        if limit <= 0:
            return ()
        records = self._call_client(
            "read recent runtime event topic",
            self._client.xrevrange,
            self._topic_stream_key(topic),
            max="+",
            min="-",
            count=limit,
        )
        return tuple(
            self._decode_topic_record(cursor, fields)
            for cursor, fields in reversed(records)
        )

    def wait_for_event_topic(
        self,
        topic: str,
        *,
        after_cursor: EventCursor | None = None,
        timeout_seconds: float,
        stop_event: ThreadEvent | None = None,
    ) -> bool:
        stream_key = self._topic_stream_key(topic)
        cursor = after_cursor or "0-0"
        remaining_seconds = max(float(timeout_seconds), 0.0)
        deadline = time.monotonic() + remaining_seconds
        while True:
            if stop_event is not None and stop_event.is_set():
                return False
            if remaining_seconds <= 0:
                response = self._call_client(
                    "wait for runtime event topic activity",
                    self._client.xread,
                    {stream_key: cursor},
                    count=1,
                )
                return bool(response)
            block_ms = min(int(remaining_seconds * 1000), self._block_ms)
            response = self._call_client(
                "wait for runtime event topic activity",
                self._client.xread,
                {stream_key: cursor},
                count=1,
                block=max(block_ms, 1),
            )
            if response:
                return True
            remaining_seconds = deadline - time.monotonic()

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
        stream_to_watch = {
            self._topic_stream_key(watch.topic): watch
            for watch in normalized
        }
        streams = {
            stream_key: watch.after_cursor or "0-0"
            for stream_key, watch in stream_to_watch.items()
        }
        remaining_seconds = max(float(timeout_seconds), 0.0)
        deadline = time.monotonic() + remaining_seconds
        while True:
            if stop_event is not None and stop_event.is_set():
                return None
            if remaining_seconds <= 0:
                response = self._call_client(
                    "wait for runtime event topic activity",
                    self._client.xread,
                    streams,
                    count=1,
                )
                if not response:
                    return None
                stream_key = str(response[0][0])
                return stream_to_watch.get(stream_key)
            block_ms = min(int(remaining_seconds * 1000), self._block_ms)
            response = self._call_client(
                "wait for runtime event topic activity",
                self._client.xread,
                streams,
                count=1,
                block=max(block_ms, 1),
            )
            if response:
                stream_key = str(response[0][0])
                return stream_to_watch.get(stream_key)
            remaining_seconds = deadline - time.monotonic()

    def read_event_topic(
        self,
        topic: str,
        *,
        after_cursor: EventCursor | None = None,
        limit: int = 100,
    ) -> tuple[EventTopicRecord, ...]:
        if limit <= 0:
            return ()
        records = self._call_client(
            "read runtime event topic",
            self._client.xrange,
            self._topic_stream_key(topic),
            min=self._cursor_min(after_cursor),
            max="+",
            count=limit,
        )
        return tuple(self._decode_topic_record(cursor, fields) for cursor, fields in records)

    def get_subscription_cursor(
        self,
        subscription_id: str,
        *,
        source_topic: str | None = None,
    ) -> EventSubscriptionCursor | None:
        normalized_id = subscription_id.strip()
        if not normalized_id:
            return None
        payload_text = self._call_client(
            "read subscription cursor",
            self._client.get,
            self._subscription_cursor_key(normalized_id),
        )
        if not payload_text:
            return None
        try:
            payload = json.loads(str(payload_text))
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        state = EventSubscriptionCursor.from_payload(payload)
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
        pattern = self._subscription_cursor_key("*")
        keys = self._list_keys(pattern)
        states: list[EventSubscriptionCursor] = []
        for key in keys:
            payload_text = self._call_client(
                "read subscription cursor",
                self._client.get,
                key,
            )
            if not payload_text:
                continue
            try:
                payload = json.loads(str(payload_text))
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            state = EventSubscriptionCursor.from_payload(payload)
            if state is None:
                continue
            if normalized_source is not None and state.source_topic != normalized_source:
                continue
            states.append(state)
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
        self._call_client(
            "write subscription cursor",
            self._client.set,
            self._subscription_cursor_key(state.subscription_id),
            json.dumps(state.to_payload(), ensure_ascii=True, separators=(",", ":")),
        )
        return state

    def _ensure_topic_listener(self, topic: str, *, start_cursor: str) -> None:
        with self._listener_lock:
            if topic in self._listener_threads:
                return
            stop_event = ThreadEvent()
            thread = Thread(
                target=self._listen_topic_stream,
                args=(topic, start_cursor, stop_event),
                name=f"events-topic-{uuid4().hex[:8]}",
                daemon=True,
            )
            self._listener_stop_events[topic] = stop_event
            self._listener_threads[topic] = thread
            thread.start()

    def _listen_topic_stream(
        self,
        topic: str,
        start_cursor: str,
        stop_event: ThreadEvent,
    ) -> None:
        stream_key = self._topic_stream_key(topic)
        cursor = start_cursor
        while not stop_event.is_set():
            try:
                response = self._client.xread(
                    {stream_key: cursor},
                    count=100,
                    block=self._block_ms,
                )
            except Exception:  # pragma: no cover - defensive logging for runtime only
                logger.exception(
                    "redis events backend failed to read topic stream",
                    extra={"topic": topic},
                )
                time.sleep(0.25)
                continue
            if not response:
                continue
            for _, items in response:
                for item_cursor, fields in items:
                    cursor = item_cursor
                    publisher_id, envelope = self._decode_envelope_record(fields)
                    if publisher_id == self._publisher_id:
                        continue
                    for handler in self._snapshot_handlers(
                        EventSelector.topic_only(topic),
                    ):
                        handler(envelope)

    def close(self) -> None:
        with self._listener_lock:
            stop_events = tuple(self._listener_stop_events.values())
            threads = tuple(self._listener_threads.values())
            self._listener_stop_events.clear()
            self._listener_threads.clear()
            self._handlers.clear()
        for stop_event in stop_events:
            stop_event.set()
        for thread in threads:
            thread.join(timeout=max(self._block_ms / 1000.0, 0.05) + 0.1)
        close_client = getattr(self._client, "close", None)
        if callable(close_client):
            close_client()

    def _snapshot_handlers(self, selector: EventSelector) -> tuple[EventHandler, ...]:
        return tuple(self._handlers.get(selector.key, ()))

    def _snapshot_stream(self, stream_key: str) -> EventCursor:
        records = self._call_client(
            "read latest stream cursor",
            self._client.xrevrange,
            stream_key,
            max="+",
            min="-",
            count=1,
        )
        if not records:
            return "0-0"
        return str(records[0][0])

    def _call_client(self, operation: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            target = self._redis_url or "the configured Redis client"
            raise RuntimeError(
                f"Redis events backend could not {operation} via {target}. "
                "Start Redis or set APP_EVENTS_BACKEND=file."
            ) from exc

    def _list_keys(self, pattern: str) -> tuple[str, ...]:
        scan_iter = getattr(self._client, "scan_iter", None)
        if callable(scan_iter):
            return tuple(str(key) for key in scan_iter(match=pattern))
        keys = getattr(self._client, "keys", None)
        if callable(keys):
            return tuple(str(key) for key in keys(pattern))
        return ()

    def _decode_envelope_record(
        self,
        fields: Mapping[str, Any],
    ) -> tuple[str | None, Event]:
        raw_record = fields.get("record")
        payload = json.loads(str(raw_record)) if raw_record else {}
        raw_envelope = payload.get("envelope") if isinstance(payload, dict) else {}
        publisher_id = payload.get("publisher_id") if isinstance(payload, dict) else None
        return (
            str(publisher_id) if isinstance(publisher_id, str) and publisher_id.strip() else None,
            Event.from_payload(dict(raw_envelope or {})),
        )

    def _decode_topic_record(
        self,
        cursor: str,
        fields: Mapping[str, Any],
    ) -> EventTopicRecord:
        _, envelope = self._decode_envelope_record(fields)
        return EventTopicRecord(cursor=str(cursor), envelope=envelope)

    def _topic_stream_key(self, topic: str) -> str:
        return f"{self._key_prefix}:topic:{topic}"

    def _dedupe_key(self, topic: str, dedupe_key: str) -> str:
        return f"{self._key_prefix}:dedupe:{topic}:{dedupe_key}"

    def _subscription_cursor_key(self, subscription_id: str) -> str:
        return f"{self._key_prefix}:subscription:{subscription_id}"

    @staticmethod
    def _normalize_watches(
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

    @staticmethod
    def _cursor_min(cursor: EventCursor | None) -> str:
        if cursor is None:
            return "-"
        return f"({cursor}"

    @staticmethod
    def _compare_cursors(left: str, right: str) -> int:
        left_ms, left_seq = RedisEventsBackend._parse_cursor(left)
        right_ms, right_seq = RedisEventsBackend._parse_cursor(right)
        if left_ms != right_ms:
            return 1 if left_ms > right_ms else -1
        if left_seq != right_seq:
            return 1 if left_seq > right_seq else -1
        return 0

    @staticmethod
    def _parse_cursor(cursor: str | None) -> tuple[int, int]:
        raw = (cursor or "0-0").strip()
        if not raw or "-" not in raw:
            return (0, 0)
        left, right = raw.split("-", 1)
        try:
            return (max(int(left), 0), max(int(right), 0))
        except ValueError:
            return (0, 0)
