from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from crxzipple.modules.events.domain import EventCursor, EventTopicRecord
from crxzipple.modules.events.application.services import EventsApplicationService
from crxzipple.shared.domain.events import Event


EventObservation = Callable[
    [EventTopicRecord],
    Event | Iterable[Event] | None,
]


@dataclass(frozen=True, slots=True)
class EventRouteSubscription:
    subscription_id: str
    source_topic: str
    after_cursor: EventCursor | None = None
    limit: int = 100


@dataclass(frozen=True, slots=True)
class EventRoutingResult:
    subscription_id: str
    source_topic: str
    source_records: tuple[EventTopicRecord, ...]
    read_count: int
    published_count: int
    last_cursor: EventCursor | None = None
    last_event_name: str | None = None


class EventRoutingApplicationService:
    def __init__(
        self,
        *,
        events_service: EventsApplicationService,
    ) -> None:
        self.events_service = events_service

    def route_subscription(
        self,
        subscription: EventRouteSubscription,
        observer: EventObservation,
    ) -> EventRoutingResult:
        limit = max(int(subscription.limit), 0)
        records = self.events_service.read_event_topic(
            subscription.source_topic,
            after_cursor=subscription.after_cursor,
            limit=limit,
        )
        if not records:
            return EventRoutingResult(
                subscription_id=subscription.subscription_id,
                source_topic=subscription.source_topic,
                source_records=(),
                read_count=0,
                published_count=0,
            )

        published_count = 0
        last_event_name: str | None = None
        for record in records:
            if record.envelope.event_name is not None:
                last_event_name = record.envelope.event_name
            for observed_event in self._observe_events(observer(record)):
                if observed_event.event_name is not None:
                    last_event_name = observed_event.event_name
                self.events_service.publish(observed_event)
                published_count += 1

        return EventRoutingResult(
            subscription_id=subscription.subscription_id,
            source_topic=subscription.source_topic,
            source_records=records,
            read_count=len(records),
            published_count=published_count,
            last_cursor=records[-1].cursor,
            last_event_name=last_event_name,
        )

    def route_managed_subscription(
        self,
        subscription: EventRouteSubscription,
        observer: EventObservation,
    ) -> EventRoutingResult:
        state = self.events_service.get_subscription_cursor(
            subscription.subscription_id,
            source_topic=subscription.source_topic,
        )
        after_cursor = (
            subscription.after_cursor
            if subscription.after_cursor is not None
            else state.cursor
            if state is not None
            else None
        )
        result = self.route_subscription(
            EventRouteSubscription(
                subscription_id=subscription.subscription_id,
                source_topic=subscription.source_topic,
                after_cursor=after_cursor,
                limit=subscription.limit,
            ),
            observer,
        )
        if result.last_cursor is not None:
            self.events_service.set_subscription_cursor(
                subscription.subscription_id,
                source_topic=subscription.source_topic,
                cursor=result.last_cursor,
            )
        return result

    def seed_subscription(
        self,
        subscription: EventRouteSubscription,
        *,
        cursor: EventCursor,
    ) -> None:
        self.events_service.set_subscription_cursor(
            subscription.subscription_id,
            source_topic=subscription.source_topic,
            cursor=cursor,
        )

    @staticmethod
    def _observe_events(
        result: Event | Iterable[Event] | None,
    ) -> tuple[Event, ...]:
        if result is None:
            return ()
        if isinstance(result, Event):
            return (result,)
        return tuple(item for item in result if isinstance(item, Event))
