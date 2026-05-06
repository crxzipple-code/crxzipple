from __future__ import annotations

from collections import defaultdict, deque
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
from threading import Event as ThreadEvent, Lock
import tempfile
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
from crxzipple.shared.domain.events import Event

logger = get_logger(__name__)


class FileBackedEventsBackend(
    EventPublisherPort,
    EventSubscriberPort,
    EventWaitPort,
    EventReadPort,
    EventSubscriptionCursorPort,
):
    def __init__(
        self,
        root_dir: str | Path,
        *,
        wait_poll_interval_seconds: float = 0.05,
        sync_writes: bool = False,
    ) -> None:
        self.root_dir = Path(root_dir).expanduser().resolve()
        self.topics_dir = self.root_dir / "topics"
        self.subscriptions_dir = self.root_dir / "subscriptions"
        self.topics_dir.mkdir(parents=True, exist_ok=True)
        self.subscriptions_dir.mkdir(parents=True, exist_ok=True)
        self.wait_poll_interval_seconds = max(float(wait_poll_interval_seconds), 0.01)
        self.sync_writes = bool(sync_writes)
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._write_lock = Lock()
        self.published_events: list[BusEvent] = []

    def publish(self, event: BusEvent) -> None:
        self.publish_many((event,))

    def publish_many(self, events: tuple[BusEvent, ...]) -> None:
        if not events:
            return
        self.published_events.extend(events)
        with self._write_lock:
            cursor_by_event_id = self._append_topic_records(events)
        for event in events:
            current_cursor = cursor_by_event_id.get(event.id)
            if current_cursor is None:
                continue
            selector = event.selector
            logger.debug(
                "publishing event through file-backed events backend",
                extra={
                    "topic": event.topic,
                    "event_name": event.event_name,
                    "kind": event.kind,
                    "cursor": current_cursor,
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

    def list_event_topics(self) -> tuple[str, ...]:
        topics: list[str] = []
        for log_path in sorted(self.topics_dir.glob("*.jsonl")):
            topic = self._read_topic_name_from_log(log_path)
            if topic is not None:
                topics.append(topic)
        return tuple(sorted(dict.fromkeys(topics)))

    def snapshot_event_topic(self, topic: str) -> EventCursor:
        return str(self._read_cursor(topic))

    def read_recent_event_topic(
        self,
        topic: str,
        *,
        limit: int = 100,
    ) -> tuple[EventTopicRecord, ...]:
        if limit <= 0:
            return ()
        log_path = self._topic_log_path(topic)
        if not log_path.exists():
            return ()
        records: deque[EventTopicRecord] = deque(maxlen=limit)
        try:
            with log_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    raw_line = line.strip()
                    if not raw_line:
                        continue
                    try:
                        payload = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue
                    record_cursor = str(payload.get("cursor") or "0")
                    raw_envelope = payload.get("envelope")
                    if not isinstance(raw_envelope, dict):
                        continue
                    records.append(
                        EventTopicRecord(
                            cursor=record_cursor,
                            envelope=Event.from_payload(raw_envelope),
                        ),
                    )
        except OSError:
            return ()
        return tuple(records)

    def wait_for_event_topic(
        self,
        topic: str,
        *,
        after_cursor: EventCursor | None = None,
        timeout_seconds: float,
        stop_event: ThreadEvent | None = None,
    ) -> bool:
        cursor_value = self._parse_cursor(after_cursor)
        if self._read_cursor(topic) > cursor_value:
            return True
        remaining = max(float(timeout_seconds), 0.0)
        deadline = time.monotonic() + remaining
        while True:
            if stop_event is not None and stop_event.is_set():
                return False
            if remaining <= 0:
                return self._read_cursor(topic) > cursor_value
            sleep_for = min(remaining, self.wait_poll_interval_seconds)
            if stop_event is not None:
                stop_event.wait(sleep_for)
            else:
                time.sleep(sleep_for)
            if self._read_cursor(topic) > cursor_value:
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
        triggered = self._first_triggered_watch(normalized)
        if triggered is not None:
            return triggered
        remaining = max(float(timeout_seconds), 0.0)
        deadline = time.monotonic() + remaining
        while True:
            if stop_event is not None and stop_event.is_set():
                return None
            if remaining <= 0:
                return self._first_triggered_watch(normalized)
            sleep_for = min(remaining, self.wait_poll_interval_seconds)
            if stop_event is not None:
                stop_event.wait(sleep_for)
            else:
                time.sleep(sleep_for)
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
        log_path = self._topic_log_path(topic)
        if not log_path.exists():
            return ()
        cursor_value = self._parse_cursor(after_cursor)
        records: list[EventTopicRecord] = []
        try:
            with log_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    raw_line = line.strip()
                    if not raw_line:
                        continue
                    try:
                        payload = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue
                    record_cursor = str(payload.get("cursor") or "0")
                    if self._parse_cursor(record_cursor) <= cursor_value:
                        continue
                    raw_envelope = payload.get("envelope")
                    if not isinstance(raw_envelope, dict):
                        continue
                    records.append(
                        EventTopicRecord(
                            cursor=record_cursor,
                            envelope=Event.from_payload(raw_envelope),
                        ),
                    )
                    if len(records) >= limit:
                        break
        except OSError:
            return ()
        return tuple(records)

    def get_subscription_cursor(
        self,
        subscription_id: str,
        *,
        source_topic: str | None = None,
    ) -> EventSubscriptionCursor | None:
        normalized_id = subscription_id.strip()
        if not normalized_id:
            return None
        state_path = self._subscription_state_path(normalized_id)
        lock_path = self._subscription_lock_path(normalized_id)
        with _file_lock(lock_path, shared=True):
            try:
                payload = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
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
        states: list[EventSubscriptionCursor] = []
        for state_path in sorted(self.subscriptions_dir.glob("*.json")):
            try:
                payload = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
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
        state_path = self._subscription_state_path(state.subscription_id)
        lock_path = self._subscription_lock_path(state.subscription_id)
        with _file_lock(lock_path, shared=False):
            _write_text_atomically(
                state_path,
                json.dumps(state.to_payload(), ensure_ascii=True, separators=(",", ":")),
                sync=self.sync_writes,
            )
        return state

    def _append_topic_records(self, events: tuple[Event, ...]) -> dict[str, int]:
        cursor_by_event_id: dict[str, int] = {}
        events_by_topic: dict[str, list[Event]] = {}
        for event in events:
            topic = event.topic
            assert topic is not None
            events_by_topic.setdefault(topic, []).append(event)
        for topic_events in events_by_topic.values():
            cursor_by_event_id.update(
                self._append_topic_records_for_topic(tuple(topic_events)),
            )
        return cursor_by_event_id

    def _append_topic_records_for_topic(self, events: tuple[Event, ...]) -> dict[str, int]:
        if not events:
            return {}
        topic = events[0].topic
        assert topic is not None
        log_path = self._topic_log_path(topic)
        cursor_path = self._topic_cursor_path(topic)
        dedupe_path = self._topic_dedupe_path(topic)
        lock_path = self._topic_lock_path(topic)
        with _file_lock(lock_path, shared=False):
            has_dedupe = any(event.dedupe_key is not None for event in events)
            dedupe_index = (
                self._read_dedupe_index_unlocked(dedupe_path)
                if has_dedupe
                else {}
            )
            current_cursor = self._read_cursor_unlocked(cursor_path)
            cursor_by_event_id: dict[str, int] = {}
            records: list[dict[str, object]] = []
            for event in events:
                if event.dedupe_key is not None:
                    existing_cursor = dedupe_index.get(event.dedupe_key)
                    if existing_cursor is not None:
                        continue
                current_cursor += 1
                cursor_by_event_id[event.id] = current_cursor
                records.append(
                    {
                        "cursor": current_cursor,
                        "envelope": event.to_payload(),
                    },
                )
                if event.dedupe_key is not None:
                    dedupe_index[event.dedupe_key] = current_cursor
            if not records:
                return cursor_by_event_id
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as handle:
                for record in records:
                    handle.write(
                        json.dumps(
                            record,
                            ensure_ascii=True,
                            separators=(",", ":"),
                        ),
                    )
                    handle.write("\n")
                handle.flush()
                if self.sync_writes:
                    os.fsync(handle.fileno())
            _write_text_atomically(cursor_path, str(current_cursor), sync=self.sync_writes)
            if has_dedupe:
                _write_text_atomically(
                    dedupe_path,
                    json.dumps(dedupe_index, ensure_ascii=True, separators=(",", ":")),
                    sync=self.sync_writes,
                )
            return cursor_by_event_id

    def _read_cursor(self, topic: str) -> int:
        cursor_path = self._topic_cursor_path(topic)
        lock_path = self._topic_lock_path(topic)
        with _file_lock(lock_path, shared=True):
            return self._read_cursor_unlocked(cursor_path)

    def _read_cursor_unlocked(self, cursor_path: Path) -> int:
        if not cursor_path.exists():
            return 0
        try:
            return max(int(cursor_path.read_text(encoding="utf-8").strip() or "0"), 0)
        except (OSError, ValueError):
            return 0

    def _topic_log_path(self, topic: str) -> Path:
        topic_key = self._topic_key(topic)
        return self.topics_dir / f"{topic_key}.jsonl"

    def _topic_cursor_path(self, topic: str) -> Path:
        topic_key = self._topic_key(topic)
        return self.topics_dir / f"{topic_key}.cursor"

    def _topic_lock_path(self, topic: str) -> Path:
        topic_key = self._topic_key(topic)
        return self.topics_dir / f"{topic_key}.lock"

    def _topic_dedupe_path(self, topic: str) -> Path:
        topic_key = self._topic_key(topic)
        return self.topics_dir / f"{topic_key}.dedupe.json"

    def _subscription_state_path(self, subscription_id: str) -> Path:
        subscription_key = self._topic_key(subscription_id)
        return self.subscriptions_dir / f"{subscription_key}.json"

    def _subscription_lock_path(self, subscription_id: str) -> Path:
        subscription_key = self._topic_key(subscription_id)
        return self.subscriptions_dir / f"{subscription_key}.lock"

    def _read_dedupe_index_unlocked(self, path: Path) -> dict[str, int]:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        resolved: dict[str, int] = {}
        for key, value in payload.items():
            if not isinstance(key, str):
                continue
            try:
                resolved[key] = max(int(value), 0)
            except (TypeError, ValueError):
                continue
        return resolved

    @staticmethod
    def _read_topic_name_from_log(path: Path) -> str | None:
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    raw_line = line.strip()
                    if not raw_line:
                        continue
                    try:
                        payload = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue
                    raw_envelope = payload.get("envelope")
                    if not isinstance(raw_envelope, dict):
                        continue
                    event = Event.from_payload(raw_envelope)
                    if isinstance(event.topic, str) and event.topic.strip():
                        return event.topic
        except OSError:
            return None
        return None

    @staticmethod
    def _topic_key(topic: str) -> str:
        return hashlib.sha1(topic.encode("utf-8")).hexdigest()

    @staticmethod
    def _parse_cursor(cursor: EventCursor | None) -> int:
        if cursor is None:
            return 0
        try:
            return max(int(cursor), 0)
        except (TypeError, ValueError):
            return 0

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

    def _first_triggered_watch(
        self,
        watches: tuple[EventTopicWatch, ...],
    ) -> EventTopicWatch | None:
        for watch in watches:
            if self._read_cursor(watch.topic) > self._parse_cursor(watch.after_cursor):
                return watch
        return None


@contextmanager
def _file_lock(path: Path, *, shared: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _write_text_atomically(path: Path, payload: str, *, sync: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_path_raw = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temp_path = Path(temp_path_raw)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            if sync:
                os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
