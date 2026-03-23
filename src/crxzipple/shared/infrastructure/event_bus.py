from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable

from crxzipple.shared.domain.events import DomainEvent
from crxzipple.core.logger import get_logger


EventHandler = Callable[[DomainEvent], None]
logger = get_logger(__name__)


class EventBus(ABC):
    @abstractmethod
    def publish(self, event: DomainEvent) -> None:
        raise NotImplementedError

    @abstractmethod
    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        raise NotImplementedError


class InMemoryEventBus(EventBus):
    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self.published_events: list[DomainEvent] = []

    def publish(self, event: DomainEvent) -> None:
        self.published_events.append(event)
        logger.debug(
            "publishing domain event",
            extra={
                "event_name": event.name,
                "payload": event.payload,
                "handler_count": len(self._handlers.get(event.name, [])),
            },
        )
        for handler in self._handlers.get(event.name, []):
            handler(event)

    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        self._handlers[event_name].append(handler)
        logger.debug(
            "registered domain event handler",
            extra={"event_name": event_name, "handler_count": len(self._handlers[event_name])},
        )
