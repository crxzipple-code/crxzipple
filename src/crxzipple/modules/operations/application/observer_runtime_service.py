from __future__ import annotations

from datetime import datetime
from threading import Event as StopEvent

from crxzipple.modules.events.domain import EventCursor, EventTopicWatch
from crxzipple.modules.operations.application.observer_cursor_state import (
    OperationsObserverCursorState,
)
from crxzipple.modules.operations.application.observer_runtime_scan_state import (
    OperationsObserverScanState,
)
from crxzipple.modules.operations.application.observer_runtime_callbacks import (
    OperationsObserverRuntimeCallbacks,
)
from crxzipple.modules.operations.application.observer_runtime_loop import (
    run_observer_until_stopped,
)
from crxzipple.modules.operations.application.observer_runtime_processing import (
    build_observer_wait_watches,
    process_available_observer_events,
    wait_for_observer_events,
)
from crxzipple.modules.operations.application.observer_subscriptions import (
    OperationsObserverBatchHandler,
    OperationsObserverHandler,
    OperationsObserverHeartbeatHandler,
    OperationsObserverMaintenanceHandler,
    OperationsObserverSubscription,
)
from crxzipple.modules.operations.application.ports import OperationsEventStreamPort
from crxzipple.modules.operations.application.observer_subscription_processor import (
    process_observer_subscription,
)
from crxzipple.shared.domain.events import named_event_topic


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
        self._start_at_tail_when_no_cursor = bool(start_at_tail_when_no_cursor)
        self._subscriptions: list[OperationsObserverSubscription] = list(
            subscriptions,
        )
        self._scan_state = OperationsObserverScanState(
            full_scan_interval_seconds=full_scan_interval_seconds,
        )
        self._cursor_state = OperationsObserverCursorState(
            events_service=events_service,
            start_at_tail_when_no_cursor=start_at_tail_when_no_cursor,
        )
        self._callbacks = OperationsObserverRuntimeCallbacks(
            runtime_name=runtime_name,
            subscription_count=lambda: len(self.subscriptions),
            heartbeat_handler=heartbeat_handler,
            maintenance_handler=maintenance_handler,
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
        self._scan_state.mark_subscription_changed()

    def process_available_events(
        self,
        *,
        limit_per_subscription: int = 100,
        from_beginning: bool = False,
        event_driven: bool = False,
    ) -> int:
        limit = max(int(limit_per_subscription), 1)
        return process_available_observer_events(
            subscriptions=self.subscriptions,
            scan_state=self._scan_state,
            process_subscription=lambda subscription: self.process_subscription(
                subscription,
                limit=limit,
                from_beginning=from_beginning,
            ),
            from_beginning=from_beginning,
            event_driven=event_driven,
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
        self._callbacks.record_heartbeat(
            worker_id=worker_id,
            status=status,
            started_at=started_at,
            processed_events=processed_events,
            idle_cycles=idle_cycles,
            poll_interval_seconds=poll_interval_seconds,
            limit_per_subscription=limit_per_subscription,
        )

    def run_maintenance(self) -> None:
        self._callbacks.run_maintenance()

    def process_subscription(
        self,
        subscription: OperationsObserverSubscription,
        *,
        limit: int = 100,
        from_beginning: bool = False,
    ) -> int:
        return process_observer_subscription(
            events_service=self.events_service,
            cursor_state=self._cursor_state,
            subscription=subscription,
            limit=limit,
            from_beginning=from_beginning,
        )

    def _subscription_cursor(
        self,
        subscription: OperationsObserverSubscription,
    ) -> EventCursor | None:
        return self._cursor_state.cursor(subscription)

    def _set_subscription_cursor(
        self,
        subscription: OperationsObserverSubscription,
        cursor: EventCursor,
    ) -> None:
        self._cursor_state.set_cursor(subscription, cursor)

    def build_wait_watches(self) -> tuple[EventTopicWatch, ...]:
        return build_observer_wait_watches(
            cursor_state=self._cursor_state,
            subscriptions=self.subscriptions,
        )

    def wait_for_events(
        self,
        *,
        timeout_seconds: float,
        stop_event: StopEvent,
    ) -> None:
        wait_for_observer_events(
            events_service=self.events_service,
            cursor_state=self._cursor_state,
            scan_state=self._scan_state,
            subscriptions=self.subscriptions,
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
        return run_observer_until_stopped(
            runtime_name=self.runtime_name,
            worker_id=worker_id,
            poll_interval_seconds=poll_interval_seconds,
            process_available_events=self.process_available_events,
            record_heartbeat=self.record_heartbeat,
            run_maintenance=self.run_maintenance,
            wait_for_events=self.wait_for_events,
            max_events=max_events,
            max_idle_cycles=max_idle_cycles,
            limit_per_subscription=limit_per_subscription,
            stop_event=stop_event,
        )
