from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Event as StopEvent

from crxzipple.core.logger import get_logger
from crxzipple.modules.events import EventsApplicationService
from crxzipple.modules.events.domain import EventTopicWatch
from crxzipple.shared.domain.events import Event, named_event_topic

logger = get_logger(__name__)

EventRelayHandler = Callable[[Event], None]


@dataclass(frozen=True, slots=True)
class EventRelaySubscription:
    subscription_id: str
    source_topic: str
    handler: EventRelayHandler
    replay_existing_on_first_run: bool = False


class EventRelayRuntimeService:
    """Durable event relay pump used by UI-facing realtime observations."""

    def __init__(
        self,
        *,
        events_service: EventsApplicationService,
        subscriptions: tuple[EventRelaySubscription, ...] = (),
        runtime_name: str = "event_relay.runtime",
    ) -> None:
        self.events_service = events_service
        self.runtime_name = runtime_name
        self._subscriptions: list[EventRelaySubscription] = list(subscriptions)

    @property
    def subscriptions(self) -> tuple[EventRelaySubscription, ...]:
        return tuple(self._subscriptions)

    def subscribe_event_name(
        self,
        event_name: str,
        *,
        subscription_id: str,
        handler: EventRelayHandler,
        replay_existing_on_first_run: bool = False,
    ) -> None:
        self.subscribe_topic(
            named_event_topic(event_name),
            subscription_id=subscription_id,
            handler=handler,
            replay_existing_on_first_run=replay_existing_on_first_run,
        )

    def subscribe_topic(
        self,
        source_topic: str,
        *,
        subscription_id: str,
        handler: EventRelayHandler,
        replay_existing_on_first_run: bool = False,
    ) -> None:
        self._subscriptions.append(
            EventRelaySubscription(
                subscription_id=subscription_id,
                source_topic=source_topic,
                handler=handler,
                replay_existing_on_first_run=replay_existing_on_first_run,
            ),
        )

    def process_available_events(self, *, limit_per_subscription: int = 100) -> int:
        limit = max(int(limit_per_subscription), 1)
        processed_count = 0
        for subscription in self.subscriptions:
            processed_count += self.process_subscription(subscription, limit=limit)
        return processed_count

    def process_subscription(
        self,
        subscription: EventRelaySubscription,
        *,
        limit: int = 100,
    ) -> int:
        state = self.events_service.get_subscription_cursor(
            subscription.subscription_id,
            source_topic=subscription.source_topic,
        )
        if state is None:
            if not subscription.replay_existing_on_first_run:
                cursor = self.events_service.snapshot_event_topic(subscription.source_topic)
                self.events_service.set_subscription_cursor(
                    subscription.subscription_id,
                    source_topic=subscription.source_topic,
                    cursor=cursor,
                )
                return 0
        records = self.events_service.read_event_topic(
            subscription.source_topic,
            after_cursor=state.cursor if state is not None else None,
            limit=max(int(limit), 1),
        )
        processed_count = 0
        last_cursor: str | None = None
        for record in records:
            try:
                subscription.handler(record.envelope)
            except Exception:
                logger.exception(
                    "event relay handler failed",
                    extra={
                        "subscription_id": subscription.subscription_id,
                        "source_topic": subscription.source_topic,
                        "source_cursor": record.cursor,
                        "event_name": record.envelope.event_name,
                    },
                )
                break
            processed_count += 1
            last_cursor = record.cursor

        if last_cursor is not None:
            self.events_service.set_subscription_cursor(
                subscription.subscription_id,
                source_topic=subscription.source_topic,
                cursor=last_cursor,
            )
        return processed_count

    def build_wait_watches(self) -> tuple[EventTopicWatch, ...]:
        watches: list[EventTopicWatch] = []
        for subscription in self.subscriptions:
            state = self.events_service.get_subscription_cursor(
                subscription.subscription_id,
                source_topic=subscription.source_topic,
            )
            watches.append(
                EventTopicWatch(
                    topic=subscription.source_topic,
                    after_cursor=state.cursor if state is not None else None,
                ),
            )
        return tuple(watches)

    def wait_for_events(
        self,
        *,
        timeout_seconds: float,
        stop_event: StopEvent,
    ) -> None:
        watches = self.build_wait_watches()
        if not watches:
            stop_event.wait(timeout_seconds)
            return
        self.events_service.wait_for_event_topics(
            watches,
            timeout_seconds=timeout_seconds,
            stop_event=stop_event,
        )

    def run_until_stopped(
        self,
        *,
        worker_id: str,
        poll_interval_seconds: float,
        max_events: int | None = None,
        max_idle_cycles: int | None = None,
        limit_per_subscription: int = 100,
        stop_event: StopEvent | None = None,
    ) -> int:
        processed_events = 0
        idle_cycles = 0
        stopper = stop_event or StopEvent()

        logger.info(
            "event relay runtime started",
            extra={
                "runtime_name": self.runtime_name,
                "poll_interval_seconds": poll_interval_seconds,
                "max_events": max_events,
                "max_idle_cycles": max_idle_cycles,
                "worker_id": worker_id,
            },
        )

        while not stopper.is_set():
            processed = self.process_available_events(
                limit_per_subscription=limit_per_subscription,
            )
            if processed <= 0:
                idle_cycles += 1
                if max_idle_cycles is not None and idle_cycles >= max_idle_cycles:
                    break
                self.wait_for_events(
                    timeout_seconds=poll_interval_seconds,
                    stop_event=stopper,
                )
                continue

            idle_cycles = 0
            processed_events += processed
            if max_events is not None and processed_events >= max_events:
                break

        logger.info(
            "event relay runtime stopped",
            extra={
                "runtime_name": self.runtime_name,
                "processed_events": processed_events,
                "worker_id": worker_id,
            },
        )
        return processed_events
