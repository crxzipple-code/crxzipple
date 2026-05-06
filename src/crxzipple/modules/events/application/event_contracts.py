from __future__ import annotations

from crxzipple.modules.events.application.contracts import EventTopicContract
from crxzipple.shared import EventDefinition, EventSurface


def events_event_topic_contracts() -> tuple[EventTopicContract, ...]:
    return ()


def events_event_definitions() -> tuple[EventDefinition, ...]:
    return ()


def events_event_surfaces() -> tuple[EventSurface, ...]:
    return ()
