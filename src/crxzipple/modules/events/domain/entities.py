from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from crxzipple.modules.events.domain.value_objects import EventOutboxStatus
from crxzipple.shared.domain import Entity, Event
from crxzipple.shared.time import coerce_utc_datetime


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(kw_only=True)
class EventOutboxRecord(Entity[str]):
    topic: str
    event_payload: dict[str, Any]
    event_name: str | None = None
    status: EventOutboxStatus = EventOutboxStatus.PENDING
    attempts: int = 0
    error_message: str | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    available_at: datetime = field(default_factory=utcnow)
    publisher_id: str | None = None
    claim_expires_at: datetime | None = None
    delivered_at: datetime | None = None

    def __post_init__(self) -> None:
        normalized_topic = self.topic.strip() if isinstance(self.topic, str) else ""
        if not normalized_topic:
            raise ValueError("Event outbox record requires a topic.")
        self.topic = normalized_topic
        self.event_payload = dict(self.event_payload)
        self.created_at = coerce_utc_datetime(self.created_at)
        self.updated_at = coerce_utc_datetime(self.updated_at)
        self.available_at = coerce_utc_datetime(self.available_at)
        self.publisher_id = self.publisher_id.strip() if self.publisher_id else None
        if self.claim_expires_at is not None:
            self.claim_expires_at = coerce_utc_datetime(self.claim_expires_at)
        if self.delivered_at is not None:
            self.delivered_at = coerce_utc_datetime(self.delivered_at)

    @classmethod
    def from_event(cls, event: Event) -> "EventOutboxRecord":
        if event.topic is None:
            raise ValueError("Event outbox record requires event.topic.")
        return cls(
            id=event.id,
            topic=event.topic,
            event_name=event.event_name,
            event_payload=event.to_payload(),
            created_at=event.created_at,
            updated_at=utcnow(),
            available_at=utcnow(),
        )

    def to_event(self) -> Event:
        return Event.from_payload(self.event_payload)

    def claim_for_publish(
        self,
        *,
        publisher_id: str,
        lease_seconds: int,
        claimed_at: datetime | None = None,
    ) -> None:
        normalized_publisher_id = publisher_id.strip()
        if not normalized_publisher_id:
            raise ValueError("Event outbox publisher_id cannot be empty.")
        now = claimed_at or utcnow()
        self.status = EventOutboxStatus.PUBLISHING
        self.publisher_id = normalized_publisher_id
        self.claim_expires_at = now + timedelta(seconds=max(int(lease_seconds), 1))
        self.updated_at = now

    def mark_delivered(self, *, delivered_at: datetime | None = None) -> None:
        now = delivered_at or utcnow()
        self.status = EventOutboxStatus.DELIVERED
        self.updated_at = now
        self.delivered_at = now
        self.error_message = None
        self.publisher_id = None
        self.claim_expires_at = None

    def mark_failed(
        self,
        message: str,
        *,
        retry_delay_seconds: int | None = None,
        failed_at: datetime | None = None,
    ) -> None:
        now = failed_at or utcnow()
        self.status = EventOutboxStatus.FAILED
        self.attempts += 1
        self.error_message = message.strip() or "event outbox publish failed"
        self.updated_at = now
        delay = retry_delay_seconds if retry_delay_seconds is not None else 0
        self.available_at = now + timedelta(seconds=max(delay, 0))
        self.publisher_id = None
        self.claim_expires_at = None
