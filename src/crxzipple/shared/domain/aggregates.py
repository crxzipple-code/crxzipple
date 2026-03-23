from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic

from crxzipple.shared.domain.entities import Entity, IdT
from crxzipple.shared.domain.events import DomainEvent


@dataclass(kw_only=True)
class AggregateRoot(Entity[IdT], Generic[IdT]):
    _events: list[DomainEvent] = field(default_factory=list, init=False, repr=False)

    def record_event(self, event: DomainEvent) -> None:
        self._events.append(event)

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events

