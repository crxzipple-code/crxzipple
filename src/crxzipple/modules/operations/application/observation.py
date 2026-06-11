from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from crxzipple.modules.events.domain import EventTopicRecord
from crxzipple.shared.domain.events import Event, NAMED_EVENT_TOPIC_PREFIX
from crxzipple.shared.event_contracts import EventDefinitionRegistry
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc

_MAX_PAYLOAD_DEPTH = 4
_MAX_PAYLOAD_ITEMS = 24
_MAX_TEXT_LENGTH = 512


@dataclass(frozen=True, slots=True)
class OperationsObservedEvent:
    id: str
    cursor: str
    topic: str
    event_name: str
    module: str
    owner: str
    kind: str
    level: str
    status: str
    entity_id: str
    run_id: str | None
    trace_id: str | None
    source_event_name: str | None
    occurred_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "cursor": self.cursor,
            "topic": self.topic,
            "event_name": self.event_name,
            "module": self.module,
            "owner": self.owner,
            "kind": self.kind,
            "level": self.level,
            "status": self.status,
            "entity_id": self.entity_id,
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "source_event_name": self.source_event_name,
            "occurred_at": format_datetime_utc(self.occurred_at),
            "payload": dict(self.payload),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "OperationsObservedEvent | None":
        event_name = _optional_text(payload.get("event_name"))
        topic = _optional_text(payload.get("topic"))
        event_id = _optional_text(payload.get("id"))
        cursor = _optional_text(payload.get("cursor"))
        module = _optional_text(payload.get("module"))
        owner = _optional_text(payload.get("owner"))
        occurred_at = _parse_datetime(payload.get("occurred_at"))
        if not all((event_name, topic, event_id, cursor, module, owner, occurred_at)):
            return None
        raw_payload = payload.get("payload")
        return cls(
            id=event_id,
            cursor=cursor,
            topic=topic,
            event_name=event_name,
            module=module,
            owner=owner,
            kind=_optional_text(payload.get("kind")) or "fact",
            level=_optional_text(payload.get("level")) or "info",
            status=_optional_text(payload.get("status")) or "observed",
            entity_id=_optional_text(payload.get("entity_id")) or event_name,
            run_id=_optional_text(payload.get("run_id")),
            trace_id=_optional_text(payload.get("trace_id")),
            source_event_name=_optional_text(payload.get("source_event_name")),
            occurred_at=occurred_at,
            payload=dict(raw_payload) if isinstance(raw_payload, dict) else {},
        )


@dataclass(frozen=True, slots=True)
class OperationsModuleObservation:
    module: str
    owner: str
    updated_at: datetime | None = None
    event_count: int = 0
    status_counts: dict[str, int] = field(default_factory=dict)
    event_name_counts: dict[str, int] = field(default_factory=dict)
    last_event_id: str | None = None
    last_event_name: str | None = None
    last_topic: str | None = None
    last_cursor: str | None = None
    last_event_at: datetime | None = None
    recent_events: tuple[OperationsObservedEvent, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "owner": self.owner,
            "updated_at": (
                format_datetime_utc(self.updated_at)
                if self.updated_at is not None
                else None
            ),
            "event_count": self.event_count,
            "status_counts": dict(self.status_counts),
            "event_name_counts": dict(self.event_name_counts),
            "last_event_id": self.last_event_id,
            "last_event_name": self.last_event_name,
            "last_topic": self.last_topic,
            "last_cursor": self.last_cursor,
            "last_event_at": (
                format_datetime_utc(self.last_event_at)
                if self.last_event_at is not None
                else None
            ),
            "recent_events": [event.to_payload() for event in self.recent_events],
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
    ) -> "OperationsModuleObservation | None":
        module = _optional_text(payload.get("module"))
        owner = _optional_text(payload.get("owner")) or module
        if module is None:
            return None
        recent_events = tuple(
            event
            for item in payload.get("recent_events", ())
            if isinstance(item, dict)
            for event in (OperationsObservedEvent.from_payload(item),)
            if event is not None
        )
        return cls(
            module=module,
            owner=owner or module,
            updated_at=_parse_datetime(payload.get("updated_at")),
            event_count=_int(payload.get("event_count")),
            status_counts=_count_map(payload.get("status_counts")),
            event_name_counts=_count_map(payload.get("event_name_counts")),
            last_event_id=_optional_text(payload.get("last_event_id")),
            last_event_name=_optional_text(payload.get("last_event_name")),
            last_topic=_optional_text(payload.get("last_topic")),
            last_cursor=_optional_text(payload.get("last_cursor")),
            last_event_at=_parse_datetime(payload.get("last_event_at")),
            recent_events=recent_events,
        )


@dataclass(frozen=True, slots=True)
class OperationsObserverHeartbeat:
    runtime_name: str
    worker_id: str
    status: str
    started_at: datetime | None
    last_seen_at: datetime
    processed_events: int = 0
    idle_cycles: int = 0
    subscription_count: int = 0
    poll_interval_seconds: float | None = None
    limit_per_subscription: int | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "runtime_name": self.runtime_name,
            "worker_id": self.worker_id,
            "status": self.status,
            "started_at": (
                format_datetime_utc(self.started_at)
                if self.started_at is not None
                else None
            ),
            "last_seen_at": format_datetime_utc(self.last_seen_at),
            "processed_events": self.processed_events,
            "idle_cycles": self.idle_cycles,
            "subscription_count": self.subscription_count,
            "poll_interval_seconds": self.poll_interval_seconds,
            "limit_per_subscription": self.limit_per_subscription,
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
    ) -> "OperationsObserverHeartbeat | None":
        runtime_name = _optional_text(payload.get("runtime_name"))
        worker_id = _optional_text(payload.get("worker_id"))
        last_seen_at = _parse_datetime(payload.get("last_seen_at"))
        if runtime_name is None or worker_id is None or last_seen_at is None:
            return None
        return cls(
            runtime_name=runtime_name,
            worker_id=worker_id,
            status=_optional_text(payload.get("status")) or "observed",
            started_at=_parse_datetime(payload.get("started_at")),
            last_seen_at=last_seen_at,
            processed_events=_int(payload.get("processed_events")),
            idle_cycles=_int(payload.get("idle_cycles")),
            subscription_count=_int(payload.get("subscription_count")),
            poll_interval_seconds=_optional_float(
                payload.get("poll_interval_seconds"),
            ),
            limit_per_subscription=(
                _int(payload.get("limit_per_subscription"))
                if payload.get("limit_per_subscription") is not None
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class OperationsProjection:
    module: str
    kind: str
    query_key: str
    updated_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "kind": self.kind,
            "query_key": self.query_key,
            "updated_at": format_datetime_utc(self.updated_at),
            "payload": dict(self.payload),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "OperationsProjection | None":
        module = _optional_text(payload.get("module"))
        kind = _optional_text(payload.get("kind"))
        query_key = _optional_text(payload.get("query_key")) or "default"
        updated_at = _parse_datetime(payload.get("updated_at"))
        raw_payload = payload.get("payload")
        if module is None or kind is None or updated_at is None:
            return None
        if not isinstance(raw_payload, dict):
            return None
        return cls(
            module=module,
            kind=kind,
            query_key=query_key,
            updated_at=updated_at,
            payload=dict(raw_payload),
        )


@dataclass(frozen=True, slots=True)
class OperationsObservationSnapshot:
    version: int
    updated_at: datetime | None
    modules: tuple[OperationsModuleObservation, ...]
    observer_heartbeats: tuple[OperationsObserverHeartbeat, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "updated_at": (
                format_datetime_utc(self.updated_at)
                if self.updated_at is not None
                else None
            ),
            "modules": [module.to_payload() for module in self.modules],
            "observer_heartbeats": [
                heartbeat.to_payload() for heartbeat in self.observer_heartbeats
            ],
        }


class OperationsObservationStore(Protocol):
    def record_observed_event(self, event: OperationsObservedEvent) -> None:
        ...

    def record_observed_events(
        self,
        events: tuple[OperationsObservedEvent, ...],
    ) -> None:
        ...

    def record_observer_heartbeat(
        self,
        heartbeat: OperationsObserverHeartbeat,
    ) -> None:
        ...

    def reset(self) -> None:
        ...

    def get_module_observation(
        self,
        module: str,
    ) -> OperationsModuleObservation | None:
        ...

    def snapshot(self) -> OperationsObservationSnapshot:
        ...

    def list_event_buckets(
        self,
        *,
        module: str | None = None,
        event_name: str | None = None,
        since: datetime | None = None,
        limit: int = 500,
    ) -> tuple[dict[str, Any], ...]:
        ...


@dataclass(frozen=True, slots=True)
class OperationsEventObserver:
    observation_store: OperationsObservationStore
    definition_registry: EventDefinitionRegistry | None = None

    def observe_event_record(self, record: EventTopicRecord) -> None:
        self.observation_store.record_observed_event(
            observed_event_from_record(
                record,
                definition_registry=self.definition_registry,
            ),
        )

    def observe_event_records(self, records: tuple[EventTopicRecord, ...]) -> None:
        self.observation_store.record_observed_events(
            tuple(
                observed_event_from_record(
                    record,
                    definition_registry=self.definition_registry,
                )
                for record in records
            ),
        )


def observed_event_from_record(
    record: EventTopicRecord,
    *,
    definition_registry: EventDefinitionRegistry | None = None,
) -> OperationsObservedEvent:
    event = record.envelope
    payload = dict(event.payload)
    event_name = _event_name(event, payload)
    definition = (
        definition_registry.get_by_event_name(event_name)
        if definition_registry is not None
        else None
    )
    owner = definition.owner if definition is not None else _owner_from_name(event_name)
    module = _module_from_owner(owner, event_name)
    status = _event_status(event_name, payload)
    trace_id = _trace_id(event, payload)
    run_id = _run_id(payload)
    entity_id = _entity_id(payload, fallback=run_id or event.id or event_name)
    source_event_name = _optional_text(payload.get("source_event_name"))
    return OperationsObservedEvent(
        id=event.id,
        cursor=record.cursor,
        topic=event.topic or record.cursor,
        event_name=event_name,
        module=module,
        owner=owner,
        kind=event.kind,
        level=_event_level(event_name, status, payload),
        status=status,
        entity_id=entity_id,
        run_id=run_id,
        trace_id=trace_id,
        source_event_name=source_event_name,
        occurred_at=coerce_utc_datetime(event.occurred_at),
        payload=_sanitize_payload(payload),
    )


def _event_name(event: Event, payload: dict[str, Any]) -> str:
    if event.event_name:
        return _normalize_event_name(event.event_name)
    payload_name = _optional_text(payload.get("event_name"))
    if payload_name:
        return _normalize_event_name(payload_name)
    if event.topic:
        return _normalize_event_name(event.topic)
    return "event"


def _normalize_event_name(value: str) -> str:
    normalized = value.strip()
    named_prefix = f"{NAMED_EVENT_TOPIC_PREFIX}."
    if normalized.startswith(named_prefix):
        return normalized[len(named_prefix):]
    return normalized


def _owner_from_name(event_name: str) -> str:
    first = event_name.split(".", 1)[0].strip().lower()
    if first == "channel":
        return "channels"
    if first == "event_relay":
        return "events"
    return first or "system"


def _module_from_owner(owner: str, event_name: str) -> str:
    normalized = owner.strip().lower().replace("_", "-")
    if normalized in {"channel", "channels"}:
        return "channels"
    if normalized in {"event", "events", "event-relay"}:
        return "events"
    if normalized:
        return normalized
    return _owner_from_name(event_name)


def _event_status(event_name: str, payload: dict[str, Any]) -> str:
    status = _optional_text(payload.get("status"))
    if status:
        return status
    tail = event_name.rsplit(".", 1)[-1].strip().lower()
    return tail.replace("_", "-") or "observed"


def _event_level(
    event_name: str,
    status: str,
    payload: dict[str, Any],
) -> str:
    explicit = _optional_text(payload.get("level"))
    if explicit in {"debug", "info", "warning", "error"}:
        return explicit
    text = f"{event_name} {status}".lower()
    if any(token in text for token in ("failed", "error", "timed_out", "dead")):
        return "error"
    if any(token in text for token in ("cancelled", "stale", "offline", "warning")):
        return "warning"
    return "info"


def _entity_id(payload: dict[str, Any], *, fallback: str) -> str:
    for key in (
        "run_id",
        "owner_id",
        "request_id",
        "tool_run_id",
        "assignment_id",
        "worker_id",
        "llm_id",
        "invocation_id",
        "source_event_id",
        "connection_id",
        "runtime_id",
        "resource_id",
        "target_id",
        "binding_id",
        "credential_binding_id",
        "audit_ref",
    ):
        value = _optional_text(payload.get(key))
        if value:
            return value
    return fallback


def _run_id(payload: dict[str, Any]) -> str | None:
    explicit = _optional_text(payload.get("run_id"))
    if explicit:
        return explicit
    owner_kind = _optional_text(payload.get("owner_kind"))
    if owner_kind == "orchestration_run":
        return _optional_text(payload.get("owner_id"))
    return None


def _trace_id(event: Event, payload: dict[str, Any]) -> str | None:
    for key in ("trace_id", "correlation_id", "source_event_id"):
        value = _optional_text(payload.get(key))
        if value:
            return value
    for key in ("trace_id", "correlation_id"):
        value = _optional_text(event.trace.get(key))
        if value:
            return value
    return None


def _sanitize_payload(value: Any, *, depth: int = 0) -> Any:
    if depth >= _MAX_PAYLOAD_DEPTH:
        return _truncate(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _truncate(value)
    if isinstance(value, datetime):
        return format_datetime_utc(value)
    if isinstance(value, dict):
        items = list(value.items())[:_MAX_PAYLOAD_ITEMS]
        return {
            str(key): _sanitize_payload(item_value, depth=depth + 1)
            for key, item_value in items
            if isinstance(key, str) and key.strip()
        }
    if isinstance(value, (list, tuple, set)):
        return [
            _sanitize_payload(item, depth=depth + 1)
            for item in list(value)[:_MAX_PAYLOAD_ITEMS]
        ]
    return _truncate(value)


def _truncate(value: Any) -> str:
    text = str(value)
    if len(text) <= _MAX_TEXT_LENGTH:
        return text
    return f"{text[:_MAX_TEXT_LENGTH]}..."


def _optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(float(value))
        except ValueError:
            return 0
    return 0


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _count_map(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): _int(item)
        for key, item in value.items()
        if isinstance(key, str) and key.strip()
    }


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return coerce_utc_datetime(datetime.fromisoformat(value))
    except ValueError:
        return None
