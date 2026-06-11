from __future__ import annotations

from threading import Event as StopEvent

from crxzipple.core.db import SessionFactory
from crxzipple.core.logger import get_logger
from crxzipple.modules.events.application import EventOutboxPublishResult
from crxzipple.modules.events.infrastructure.persistence.repositories import (
    SqlAlchemyEventOutboxRepository,
)
from crxzipple.shared.infrastructure.event_bus import EventBus

logger = get_logger(__name__)


class EventOutboxPublisherService:
    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        event_bus: EventBus,
        retry_base_delay_seconds: int = 1,
        retry_max_delay_seconds: int = 60,
    ) -> None:
        self.session_factory = session_factory
        self.event_bus = event_bus
        self.retry_base_delay_seconds = max(int(retry_base_delay_seconds), 0)
        self.retry_max_delay_seconds = max(int(retry_max_delay_seconds), 0)

    def publish_available(self, *, limit: int = 100) -> EventOutboxPublishResult:
        return self.publish_available_for_publisher(
            publisher_id="event-outbox-publisher",
            limit=limit,
        )

    def publish_available_for_publisher(
        self,
        *,
        publisher_id: str,
        limit: int = 100,
        claim_seconds: int = 60,
    ) -> EventOutboxPublishResult:
        published = 0
        failed = 0
        with self.session_factory() as session:
            repo = SqlAlchemyEventOutboxRepository(session)
            records = repo.claim_publishable(
                publisher_id=publisher_id,
                limit=max(int(limit), 1),
                claim_seconds=claim_seconds,
            )
            session.commit()
            for record in records:
                try:
                    self.event_bus.publish(record.to_event())
                except Exception as exc:
                    delay = self._retry_delay_seconds(record.attempts)
                    record.mark_failed(str(exc), retry_delay_seconds=delay)
                    failed += 1
                    logger.exception(
                        "event outbox publish failed",
                        extra={
                            "event_outbox_record_id": record.id,
                            "event_name": record.event_name,
                            "topic": record.topic,
                            "retry_delay_seconds": delay,
                        },
                    )
                else:
                    record.mark_delivered()
                    published += 1
                repo.add(record)
            session.commit()
        return EventOutboxPublishResult(published=published, failed=failed)

    def run_until_stopped(
        self,
        *,
        worker_id: str,
        poll_interval_seconds: float,
        max_events: int | None = None,
        max_idle_cycles: int | None = None,
        limit: int = 100,
        stop_event: StopEvent | None = None,
    ) -> int:
        processed_events = 0
        idle_cycles = 0
        stopper = stop_event or StopEvent()

        logger.info(
            "event outbox publisher started",
            extra={
                "worker_id": worker_id,
                "poll_interval_seconds": poll_interval_seconds,
                "max_events": max_events,
                "max_idle_cycles": max_idle_cycles,
            },
        )
        while not stopper.is_set():
            result = self.publish_available_for_publisher(
                publisher_id=worker_id,
                limit=limit,
            )
            if result.processed <= 0:
                idle_cycles += 1
                if max_idle_cycles is not None and idle_cycles >= max_idle_cycles:
                    break
                stopper.wait(max(float(poll_interval_seconds), 0.0))
                continue

            idle_cycles = 0
            processed_events += result.processed
            if max_events is not None and processed_events >= max_events:
                break

        logger.info(
            "event outbox publisher stopped",
            extra={"worker_id": worker_id, "processed_events": processed_events},
        )
        return processed_events

    def _retry_delay_seconds(self, attempts: int) -> int:
        if self.retry_base_delay_seconds <= 0 or self.retry_max_delay_seconds <= 0:
            return 0
        return min(
            self.retry_max_delay_seconds,
            self.retry_base_delay_seconds * (2 ** max(int(attempts), 0)),
        )
