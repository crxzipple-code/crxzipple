from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic

from crxzipple.shared.domain.entities import Entity, IdT
from crxzipple.shared.domain.events import Event


@dataclass(kw_only=True)
class AggregateRoot(Entity[IdT], Generic[IdT]):
    _events: list[Event] = field(default_factory=list, init=False, repr=False)

    def record_event(self, event: Event) -> None:
        self._events.append(event)

    def pending_events(self) -> list[Event]:
        return list(self._events)

    def clear_events(self) -> None:
        self._events.clear()

    def pull_events(self) -> list[Event]:
        events = list(self._events)
        self._events.clear()
        return events
