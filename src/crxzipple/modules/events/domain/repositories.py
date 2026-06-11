from __future__ import annotations

from datetime import datetime
from typing import Protocol

from crxzipple.modules.events.domain.entities import EventOutboxRecord
from crxzipple.modules.events.domain.value_objects import EventOutboxStatus


class EventOutboxRepository(Protocol):
    def add(self, record: EventOutboxRecord) -> None:
        ...

    def get(self, record_id: str) -> EventOutboxRecord | None:
        ...

    def list_publishable(
        self,
        *,
        limit: int = 100,
        now: datetime | None = None,
    ) -> list[EventOutboxRecord]:
        ...

    def claim_publishable(
        self,
        *,
        publisher_id: str,
        limit: int = 100,
        claim_seconds: int = 60,
        now: datetime | None = None,
    ) -> list[EventOutboxRecord]:
        ...

    def list(
        self,
        *,
        status: EventOutboxStatus | None = None,
        limit: int = 100,
    ) -> list[EventOutboxRecord]:
        ...
