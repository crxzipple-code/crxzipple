from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from crxzipple.modules.operations.application.observation_payloads import (
    count_map,
    int_value,
    optional_text,
    parse_datetime,
)
from crxzipple.shared.time import format_datetime_utc


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
        event_name = optional_text(payload.get("event_name"))
        topic = optional_text(payload.get("topic"))
        event_id = optional_text(payload.get("id"))
        cursor = optional_text(payload.get("cursor"))
        module = optional_text(payload.get("module"))
        owner = optional_text(payload.get("owner"))
        occurred_at = parse_datetime(payload.get("occurred_at"))
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
            kind=optional_text(payload.get("kind")) or "fact",
            level=optional_text(payload.get("level")) or "info",
            status=optional_text(payload.get("status")) or "observed",
            entity_id=optional_text(payload.get("entity_id")) or event_name,
            run_id=optional_text(payload.get("run_id")),
            trace_id=optional_text(payload.get("trace_id")),
            source_event_name=optional_text(payload.get("source_event_name")),
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
        module = optional_text(payload.get("module"))
        owner = optional_text(payload.get("owner")) or module
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
            updated_at=parse_datetime(payload.get("updated_at")),
            event_count=int_value(payload.get("event_count")),
            status_counts=count_map(payload.get("status_counts")),
            event_name_counts=count_map(payload.get("event_name_counts")),
            last_event_id=optional_text(payload.get("last_event_id")),
            last_event_name=optional_text(payload.get("last_event_name")),
            last_topic=optional_text(payload.get("last_topic")),
            last_cursor=optional_text(payload.get("last_cursor")),
            last_event_at=parse_datetime(payload.get("last_event_at")),
            recent_events=recent_events,
        )
