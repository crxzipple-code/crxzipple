from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Event as StopEvent

from crxzipple.core.logger import get_logger
from crxzipple.modules.events.domain import EventTopicWatch
from crxzipple.modules.orchestration.application.ports import (
    EventSubscriptionStreamPort,
)
from crxzipple.shared.domain.events import Event, named_event_topic

logger = get_logger(__name__)

RuntimeEventHandler = Callable[[Event], None]


@dataclass(frozen=True, slots=True)
class OrchestrationRuntimeEventSubscription:
    subscription_id: str
    source_topic: str
    handler: RuntimeEventHandler


class OrchestrationRuntimeEventService:
    """Owned event pump for orchestration runtime event subscriptions."""

    def __init__(
        self,
        *,
        events_service: EventSubscriptionStreamPort,
        subscriptions: tuple[OrchestrationRuntimeEventSubscription, ...] = (),
        runtime_name: str = "orchestration.runtime",
    ) -> None:
        self.events_service = events_service
        self.runtime_name = runtime_name
        self._subscriptions: list[OrchestrationRuntimeEventSubscription] = list(
            subscriptions,
        )

    @property
    def subscriptions(self) -> tuple[OrchestrationRuntimeEventSubscription, ...]:
        return tuple(self._subscriptions)

    def subscribe_event_name(
        self,
        event_name: str,
        *,
        subscription_id: str,
        handler: RuntimeEventHandler,
    ) -> None:
        self.subscribe_topic(
            named_event_topic(event_name),
            subscription_id=subscription_id,
            handler=handler,
        )

    def subscribe_topic(
        self,
        source_topic: str,
        *,
        subscription_id: str,
        handler: RuntimeEventHandler,
    ) -> None:
        self._subscriptions.append(
            OrchestrationRuntimeEventSubscription(
                subscription_id=subscription_id,
                source_topic=source_topic,
                handler=handler,
            ),
        )

    def process_available_events(self, *, limit_per_subscription: int = 100) -> int:
        limit = max(int(limit_per_subscription), 1)
        processed_count = 0
        for subscription in self.subscriptions:
            processed_count += self.process_subscription(
                subscription,
                limit=limit,
            )
        return processed_count

    def process_subscription(
        self,
        subscription: OrchestrationRuntimeEventSubscription,
        *,
        limit: int = 100,
    ) -> int:
        state = self.events_service.get_subscription_cursor(
            subscription.subscription_id,
            source_topic=subscription.source_topic,
        )
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
                    "orchestration runtime event handler failed",
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
            "orchestration runtime event service started",
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
                    logger.info(
                        "orchestration runtime event service exiting after idle limit",
                        extra={
                            "runtime_name": self.runtime_name,
                            "idle_cycles": idle_cycles,
                            "worker_id": worker_id,
                        },
                    )
                    break
                self.wait_for_events(
                    timeout_seconds=poll_interval_seconds,
                    stop_event=stopper,
                )
                continue

            idle_cycles = 0
            processed_events += processed
            logger.info(
                "orchestration runtime event service processed events",
                extra={
                    "runtime_name": self.runtime_name,
                    "processed": processed,
                    "processed_events": processed_events,
                    "worker_id": worker_id,
                },
            )
            if max_events is not None and processed_events >= max_events:
                logger.info(
                    "orchestration runtime event service exiting after event limit",
                    extra={
                        "runtime_name": self.runtime_name,
                        "processed_events": processed_events,
                        "worker_id": worker_id,
                    },
                )
                break

        return processed_events
