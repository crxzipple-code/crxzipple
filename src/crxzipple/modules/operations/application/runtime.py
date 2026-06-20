from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Event as StopEvent
import time

from crxzipple.core.logger import get_logger
from crxzipple.modules.access.application.events import ACCESS_OPERATION_EVENT_NAMES
from crxzipple.modules.browser.application.events import BROWSER_OPERATION_EVENT_NAMES
from crxzipple.modules.memory.application.events import MEMORY_OPERATION_EVENT_NAMES
from crxzipple.modules.events.domain import EventTopicRecord, EventTopicWatch
from crxzipple.modules.operations.application.observation import (
    OperationsObserverHeartbeat,
)
from crxzipple.modules.operations.application.event_contracts import (
    OPERATIONS_PROJECTION_INVALIDATED_EVENT,
)
from crxzipple.modules.operations.application.ports import OperationsEventStreamPort
from crxzipple.modules.operations.application.orchestration_observation import (
    ORCHESTRATION_OPERATIONAL_EVENT_NAMES,
)
from crxzipple.modules.skills.application.events import SKILL_OPERATION_EVENT_NAMES
from crxzipple.shared import (
    ORCHESTRATION_RUN_LLM_TEXT_DELTA_EVENT,
    ORCHESTRATION_RUN_OBSERVATION_EVENT_NAMES,
    ORCHESTRATION_RUN_TOOL_UPDATED_EVENT,
    ORCHESTRATION_RUNTIME_OBSERVATION_SOURCE_EVENT_NAMES,
    ORCHESTRATION_RUNTIME_STATUS_EVENT,
    SESSION_ITEM_APPENDED_SOURCE_EVENT,
    TOOL_RUN_OBSERVATION_SOURCE_EVENT_NAMES,
)
from crxzipple.shared.domain.events import named_event_topic
from crxzipple.shared.event_contracts import (
    EventDefinitionRegistry,
    TOOL_CLI_EVENT_NAMES,
    TOOL_FUNCTION_EVENT_NAMES,
    TOOL_SOURCE_EVENT_NAMES,
)

logger = get_logger(__name__)

OperationsObserverHandler = Callable[[EventTopicRecord], None]
OperationsObserverBatchHandler = Callable[[tuple[EventTopicRecord, ...]], None]
OperationsObserverHeartbeatHandler = Callable[[OperationsObserverHeartbeat], None]
OperationsObserverMaintenanceHandler = Callable[[], None]

_OPERATIONS_OBSERVER_STATIC_EVENT_NAMES: tuple[str, ...] = (
    *ORCHESTRATION_OPERATIONAL_EVENT_NAMES,
    *ORCHESTRATION_RUN_OBSERVATION_EVENT_NAMES,
    SESSION_ITEM_APPENDED_SOURCE_EVENT,
    ORCHESTRATION_RUN_TOOL_UPDATED_EVENT,
    ORCHESTRATION_RUN_LLM_TEXT_DELTA_EVENT,
    ORCHESTRATION_RUNTIME_STATUS_EVENT,
    *ORCHESTRATION_RUNTIME_OBSERVATION_SOURCE_EVENT_NAMES,
    *TOOL_RUN_OBSERVATION_SOURCE_EVENT_NAMES,
    "dispatch.task.queued",
    "dispatch.task.requeued",
    "dispatch.task.recovered",
    "tool.enabled",
    "tool.disabled",
    *TOOL_SOURCE_EVENT_NAMES,
    *TOOL_FUNCTION_EVENT_NAMES,
    *TOOL_CLI_EVENT_NAMES,
    "tool.assignment.created",
    "tool.assignment.started",
    "tool.assignment.succeeded",
    "tool.assignment.failed",
    "tool.assignment.cancelled",
    "tool.assignment.expired",
    "tool.worker.registered",
    "tool.worker.capabilities_updated",
    "tool.worker.recovered",
    "tool.worker.pruned",
    "tool.worker.stale",
    "llm.profile_registered",
    "llm.profile_updated",
    "llm.profile_warmup_succeeded",
    "llm.profile_warmup_skipped",
    "llm.profile_warmup_failed",
    "llm.invocation_started",
    "llm.invocation_provider_request_prepared",
    "llm.invocation_succeeded",
    "llm.invocation_failed",
    "llm.stream_delta_observed",
    "orchestration.llm_resolved",
    "channel.connection.subscription_updated",
    "channel.observation.dead_lettered",
    *MEMORY_OPERATION_EVENT_NAMES,
    *ACCESS_OPERATION_EVENT_NAMES,
    *SKILL_OPERATION_EVENT_NAMES,
    *BROWSER_OPERATION_EVENT_NAMES,
)


@dataclass(frozen=True, slots=True)
class OperationsObserverSubscription:
    subscription_id: str
    source_topic: str
    handler: OperationsObserverHandler
    batch_handler: OperationsObserverBatchHandler | None = None


class OperationsObserverRuntimeService:
    """Durable event pump that materializes operations-facing observations."""

    def __init__(
        self,
        *,
        events_service: OperationsEventStreamPort,
        subscriptions: tuple[OperationsObserverSubscription, ...] = (),
        runtime_name: str = "operations.observer",
        heartbeat_handler: OperationsObserverHeartbeatHandler | None = None,
        maintenance_handler: OperationsObserverMaintenanceHandler | None = None,
        full_scan_interval_seconds: float = 60.0,
        start_at_tail_when_no_cursor: bool = False,
    ) -> None:
        self.events_service = events_service
        self.runtime_name = runtime_name
        self._heartbeat_handler = heartbeat_handler
        self._maintenance_handler = maintenance_handler
        self._full_scan_interval_seconds = max(float(full_scan_interval_seconds), 1.0)
        self._start_at_tail_when_no_cursor = bool(start_at_tail_when_no_cursor)
        self._full_scan_completed = False
        self._last_full_scan_at = 0.0
        self._wakeup_topics: set[str] = set()
        self._subscription_cursors: dict[tuple[str, str], str | None] = {}
        self._subscriptions: list[OperationsObserverSubscription] = list(
            subscriptions,
        )

    @property
    def subscriptions(self) -> tuple[OperationsObserverSubscription, ...]:
        return tuple(self._subscriptions)

    def subscribe_event_name(
        self,
        event_name: str,
        *,
        subscription_id: str,
        handler: OperationsObserverHandler,
        batch_handler: OperationsObserverBatchHandler | None = None,
    ) -> None:
        self.subscribe_topic(
            named_event_topic(event_name),
            subscription_id=subscription_id,
            handler=handler,
            batch_handler=batch_handler,
        )

    def subscribe_topic(
        self,
        source_topic: str,
        *,
        subscription_id: str,
        handler: OperationsObserverHandler,
        batch_handler: OperationsObserverBatchHandler | None = None,
    ) -> None:
        subscription = OperationsObserverSubscription(
            subscription_id=subscription_id,
            source_topic=source_topic,
            handler=handler,
            batch_handler=batch_handler,
        )
        self._subscriptions.append(subscription)
        if self._start_at_tail_when_no_cursor:
            self._subscription_cursor(subscription)
        self._full_scan_completed = False

    def process_available_events(
        self,
        *,
        limit_per_subscription: int = 100,
        from_beginning: bool = False,
        event_driven: bool = False,
    ) -> int:
        limit = max(int(limit_per_subscription), 1)
        processed_count = 0
        subscriptions = self.subscriptions
        if not from_beginning and self._wakeup_topics:
            wakeup_topics = set(self._wakeup_topics)
            self._wakeup_topics.clear()
            for subscription in subscriptions:
                if subscription.source_topic not in wakeup_topics:
                    continue
                processed_count += self.process_subscription(
                    subscription,
                    limit=limit,
                    from_beginning=False,
                )
            if event_driven and processed_count > 0:
                return processed_count

        if event_driven and not self._should_full_scan(from_beginning=from_beginning):
            return processed_count

        for subscription in subscriptions:
            processed_count += self.process_subscription(
                subscription,
                limit=limit,
                from_beginning=from_beginning,
            )
        self._full_scan_completed = True
        self._last_full_scan_at = time.monotonic()
        return processed_count

    def _should_full_scan(self, *, from_beginning: bool) -> bool:
        if from_beginning or not self._full_scan_completed:
            return True
        return (
            time.monotonic() - self._last_full_scan_at
            >= self._full_scan_interval_seconds
        )

    def record_heartbeat(
        self,
        *,
        worker_id: str,
        status: str,
        started_at: datetime | None = None,
        processed_events: int = 0,
        idle_cycles: int = 0,
        poll_interval_seconds: float | None = None,
        limit_per_subscription: int | None = None,
    ) -> None:
        if self._heartbeat_handler is None:
            return
        heartbeat = OperationsObserverHeartbeat(
            runtime_name=self.runtime_name,
            worker_id=worker_id,
            status=status,
            started_at=started_at,
            last_seen_at=datetime.now(timezone.utc),
            processed_events=max(int(processed_events), 0),
            idle_cycles=max(int(idle_cycles), 0),
            subscription_count=len(self.subscriptions),
            poll_interval_seconds=poll_interval_seconds,
            limit_per_subscription=limit_per_subscription,
        )
        try:
            self._heartbeat_handler(heartbeat)
        except Exception:
            logger.exception(
                "operations observer heartbeat handler failed",
                extra={
                    "runtime_name": self.runtime_name,
                    "worker_id": worker_id,
                    "status": status,
                },
            )

    def run_maintenance(self) -> None:
        if self._maintenance_handler is None:
            return
        try:
            self._maintenance_handler()
        except Exception:
            logger.exception(
                "operations observer maintenance handler failed",
                extra={"runtime_name": self.runtime_name},
            )

    def process_subscription(
        self,
        subscription: OperationsObserverSubscription,
        *,
        limit: int = 100,
        from_beginning: bool = False,
    ) -> int:
        cursor = self._subscription_cursor(subscription)
        records = self.events_service.read_event_topic(
            subscription.source_topic,
            after_cursor=(
                None
                if from_beginning
                else cursor
            ),
            limit=max(int(limit), 1),
        )
        processed_count = 0
        last_cursor: str | None = None
        if records and subscription.batch_handler is not None:
            try:
                subscription.batch_handler(records)
            except Exception:
                logger.exception(
                    "operations observer batch handler failed",
                    extra={
                        "subscription_id": subscription.subscription_id,
                        "source_topic": subscription.source_topic,
                        "record_count": len(records),
                        "first_source_cursor": records[0].cursor,
                        "last_source_cursor": records[-1].cursor,
                    },
                )
                return 0
            last_cursor = records[-1].cursor
            processed_count = len(records)
            self.events_service.set_subscription_cursor(
                subscription.subscription_id,
                source_topic=subscription.source_topic,
                cursor=last_cursor,
            )
            self._set_subscription_cursor(subscription, last_cursor)
            return processed_count

        for record in records:
            try:
                subscription.handler(record)
            except Exception:
                logger.exception(
                    "operations observer handler failed",
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
            self._set_subscription_cursor(subscription, last_cursor)
        return processed_count

    def _subscription_cursor(
        self,
        subscription: OperationsObserverSubscription,
    ) -> str | None:
        key = (subscription.subscription_id, subscription.source_topic)
        if key not in self._subscription_cursors:
            state = self.events_service.get_subscription_cursor(
                subscription.subscription_id,
                source_topic=subscription.source_topic,
            )
            if state is not None:
                self._subscription_cursors[key] = state.cursor
            elif self._start_at_tail_when_no_cursor:
                cursor = self.events_service.snapshot_event_topic(
                    subscription.source_topic,
                )
                self.events_service.set_subscription_cursor(
                    subscription.subscription_id,
                    source_topic=subscription.source_topic,
                    cursor=cursor,
                )
                self._subscription_cursors[key] = cursor
            else:
                self._subscription_cursors[key] = None
        return self._subscription_cursors[key]

    def _set_subscription_cursor(
        self,
        subscription: OperationsObserverSubscription,
        cursor: str,
    ) -> None:
        self._subscription_cursors[
            (subscription.subscription_id, subscription.source_topic)
        ] = cursor

    def build_wait_watches(self) -> tuple[EventTopicWatch, ...]:
        watches: list[EventTopicWatch] = []
        for subscription in self.subscriptions:
            cursor = self._subscription_cursor(subscription)
            watches.append(
                EventTopicWatch(
                    topic=subscription.source_topic,
                    after_cursor=cursor,
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
        triggered = self.events_service.wait_for_event_topics(
            watches,
            timeout_seconds=timeout_seconds,
            stop_event=stop_event,
        )
        if triggered is not None:
            self._wakeup_topics.add(triggered.topic)

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
        started_at = datetime.now(timezone.utc)
        final_status = "stopped"

        logger.info(
            "operations observer runtime started",
            extra={
                "runtime_name": self.runtime_name,
                "poll_interval_seconds": poll_interval_seconds,
                "max_events": max_events,
                "max_idle_cycles": max_idle_cycles,
                "worker_id": worker_id,
            },
        )
        self.record_heartbeat(
            worker_id=worker_id,
            status="running",
            started_at=started_at,
            processed_events=processed_events,
            idle_cycles=idle_cycles,
            poll_interval_seconds=poll_interval_seconds,
            limit_per_subscription=limit_per_subscription,
        )

        try:
            while not stopper.is_set():
                processed = self.process_available_events(
                    limit_per_subscription=limit_per_subscription,
                    event_driven=True,
                )
                self.run_maintenance()
                if processed <= 0:
                    idle_cycles += 1
                    self.record_heartbeat(
                        worker_id=worker_id,
                        status="idle",
                        started_at=started_at,
                        processed_events=processed_events,
                        idle_cycles=idle_cycles,
                        poll_interval_seconds=poll_interval_seconds,
                        limit_per_subscription=limit_per_subscription,
                    )
                    if max_idle_cycles is not None and idle_cycles >= max_idle_cycles:
                        break
                    self.wait_for_events(
                        timeout_seconds=poll_interval_seconds,
                        stop_event=stopper,
                    )
                    continue

                idle_cycles = 0
                processed_events += processed
                self.record_heartbeat(
                    worker_id=worker_id,
                    status="running",
                    started_at=started_at,
                    processed_events=processed_events,
                    idle_cycles=idle_cycles,
                    poll_interval_seconds=poll_interval_seconds,
                    limit_per_subscription=limit_per_subscription,
                )
                if max_events is not None and processed_events >= max_events:
                    break
        except Exception:
            final_status = "failed"
            raise
        finally:
            self.record_heartbeat(
                worker_id=worker_id,
                status=final_status,
                started_at=started_at,
                processed_events=processed_events,
                idle_cycles=idle_cycles,
                poll_interval_seconds=poll_interval_seconds,
                limit_per_subscription=limit_per_subscription,
            )

        logger.info(
            "operations observer runtime stopped",
            extra={
                "runtime_name": self.runtime_name,
                "processed_events": processed_events,
                "worker_id": worker_id,
            },
        )
        return processed_events


def operations_observer_event_names(
    definition_registry: EventDefinitionRegistry | None = None,
) -> tuple[str, ...]:
    excluded = {OPERATIONS_PROJECTION_INVALIDATED_EVENT}
    names: list[str] = []
    if definition_registry is not None:
        names.extend(
            definition.event_name
            for definition in definition_registry.list_definitions()
            if definition.durability == "persistent"
            and definition.event_name not in excluded
        )
    names.extend(_OPERATIONS_OBSERVER_STATIC_EVENT_NAMES)
    return tuple(
        dict.fromkeys(
            name.strip()
            for name in names
            if isinstance(name, str) and name.strip() and name not in excluded
        ),
    )
