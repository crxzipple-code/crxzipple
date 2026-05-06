from __future__ import annotations

from abc import ABC, abstractmethod

from crxzipple.modules.events import (
    EventSelector,
    EventsApplicationService,
    InMemoryEventsBackend,
)
from crxzipple.modules.events.application.ports import BusEvent, EventHandler


class EventBus(ABC):
    @abstractmethod
    def publish(self, event: BusEvent) -> None:
        raise NotImplementedError

    @abstractmethod
    def publish_many(self, events: tuple[BusEvent, ...]) -> None:
        raise NotImplementedError

    @abstractmethod
    def subscribe(self, selector: EventSelector, handler: EventHandler) -> None:
        raise NotImplementedError


class InMemoryEventBus(EventBus):
    def __init__(self, service: EventsApplicationService | None = None) -> None:
        self._service = service or EventsApplicationService(InMemoryEventsBackend())

    def publish(self, event: BusEvent) -> None:
        self._service.publish(event)

    def publish_many(self, events: tuple[BusEvent, ...]) -> None:
        self._service.publish_many(events)

    def subscribe(self, selector: EventSelector, handler: EventHandler) -> None:
        self._service.subscribe(selector, handler)

    @property
    def events_service(self) -> EventsApplicationService:
        return self._service

    @property
    def published_events(self) -> list[BusEvent]:
        backend = self._service.backend
        published = getattr(backend, "published_events", None)
        if isinstance(published, list):
            return published
        return []


class EventsBackedEventBus(EventBus):
    def __init__(self, service: EventsApplicationService) -> None:
        self._service = service

    def publish(self, event: BusEvent) -> None:
        self._service.publish(event)

    def publish_many(self, events: tuple[BusEvent, ...]) -> None:
        self._service.publish_many(events)

    def subscribe(self, selector: EventSelector, handler: EventHandler) -> None:
        self._service.subscribe(selector, handler)

    @property
    def events_service(self) -> EventsApplicationService:
        return self._service

    @property
    def published_events(self) -> list[BusEvent]:
        backend = self._service.backend
        published = getattr(backend, "published_events", None)
        if isinstance(published, list):
            return published
        return []
