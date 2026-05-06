from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc

if TYPE_CHECKING:
    from crxzipple.modules.events.domain import EventSelector, EventTarget

VALID_EVENT_KINDS = frozenset(
    {
        "command",
        "fact",
        "broadcast",
        "observe",
        "live",
    }
)

NAMED_EVENT_TOPIC_PREFIX = "events.named"


def named_event_topic(event_name: str) -> str:
    normalized = event_name.strip() if isinstance(event_name, str) else ""
    if not normalized:
        raise ValueError("event_name is required to derive a named event topic.")
    return f"{NAMED_EVENT_TOPIC_PREFIX}.{normalized}"


@dataclass(frozen=True, slots=True)
class Event:
    name: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    topic: str | None = None
    kind: str = "fact"
    target: EventTarget | None = None
    ordering_key: str | None = None
    dedupe_key: str | None = None
    trace: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self) -> None:
        normalized_name = self.name.strip() if isinstance(self.name, str) else ""
        normalized_topic = (
            self.topic.strip()
            if isinstance(self.topic, str) and self.topic.strip()
            else None
        )
        if not normalized_name and normalized_topic is None:
            raise ValueError("Event requires either a name or a topic.")
        if normalized_topic is None and normalized_name:
            normalized_topic = named_event_topic(normalized_name)
        normalized_kind = (
            self.kind.strip()
            if isinstance(self.kind, str) and self.kind.strip()
            else "fact"
        )
        if normalized_kind not in VALID_EVENT_KINDS:
            normalized_kind = "fact"
        occurred_at = coerce_utc_datetime(self.occurred_at)
        object.__setattr__(self, "name", normalized_name)
        object.__setattr__(self, "topic", normalized_topic)
        object.__setattr__(self, "kind", normalized_kind)
        object.__setattr__(self, "occurred_at", occurred_at)

    @property
    def event_name(self) -> str | None:
        if self.name:
            return self.name
        value = self.payload.get("event_name")
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return None

    @property
    def created_at(self) -> datetime:
        return self.occurred_at

    @property
    def selector(self):
        from crxzipple.modules.events.domain import EventSelector

        assert self.topic is not None
        return EventSelector.topic_only(self.topic)

    def to_payload(self) -> dict[str, Any]:
        target = self.target
        return {
            "id": self.id,
            "name": self.name or None,
            "topic": self.topic,
            "kind": self.kind,
            "payload": dict(self.payload),
            "target": target.to_payload() if target is not None else None,
            "ordering_key": self.ordering_key,
            "dedupe_key": self.dedupe_key,
            "trace": dict(self.trace),
            "created_at": format_datetime_utc(self.occurred_at),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "Event":
        from crxzipple.modules.events.domain import EventAddress

        raw_target = payload.get("target")
        raw_created_at = payload.get("created_at")
        occurred_at = (
            datetime.fromisoformat(raw_created_at)
            if isinstance(raw_created_at, str) and raw_created_at.strip()
            else datetime.now(timezone.utc)
        )
        occurred_at = coerce_utc_datetime(occurred_at)
        return cls(
            id=str(payload.get("id") or uuid4().hex),
            name=payload.get("name") if isinstance(payload.get("name"), str) else "",
            topic=payload.get("topic") if isinstance(payload.get("topic"), str) else None,
            kind=payload.get("kind") if isinstance(payload.get("kind"), str) else "fact",
            payload=dict(payload.get("payload") or {}),
            target=EventAddress.from_payload(raw_target) if isinstance(raw_target, dict) else None,
            ordering_key=payload.get("ordering_key") if isinstance(payload.get("ordering_key"), str) else None,
            dedupe_key=payload.get("dedupe_key") if isinstance(payload.get("dedupe_key"), str) else None,
            trace=dict(payload.get("trace") or {}),
            occurred_at=occurred_at,
        )
