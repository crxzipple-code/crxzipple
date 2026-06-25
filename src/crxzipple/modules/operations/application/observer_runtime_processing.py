from __future__ import annotations

from collections.abc import Callable, Sequence
from threading import Event as StopEvent

from crxzipple.modules.events.domain import EventTopicWatch
from crxzipple.modules.operations.application.observer_cursor_state import (
    OperationsObserverCursorState,
)
from crxzipple.modules.operations.application.observer_runtime_scan_state import (
    OperationsObserverScanState,
)
from crxzipple.modules.operations.application.observer_subscriptions import (
    OperationsObserverSubscription,
)
from crxzipple.modules.operations.application.ports import OperationsEventStreamPort


def process_available_observer_events(
    *,
    subscriptions: Sequence[OperationsObserverSubscription],
    scan_state: OperationsObserverScanState,
    process_subscription: Callable[
        [OperationsObserverSubscription],
        int,
    ],
    from_beginning: bool,
    event_driven: bool,
) -> int:
    processed_count = 0
    if not from_beginning:
        wakeup_topics = scan_state.pop_wakeup_topics()
        for subscription in subscriptions:
            if subscription.source_topic not in wakeup_topics:
                continue
            processed_count += process_subscription(subscription)
        if event_driven and processed_count > 0:
            return processed_count

    if event_driven and not scan_state.should_full_scan(
        from_beginning=from_beginning,
    ):
        return processed_count

    for subscription in subscriptions:
        processed_count += process_subscription(subscription)
    scan_state.mark_full_scan_completed()
    return processed_count


def build_observer_wait_watches(
    *,
    cursor_state: OperationsObserverCursorState,
    subscriptions: Sequence[OperationsObserverSubscription],
) -> tuple[EventTopicWatch, ...]:
    return cursor_state.build_wait_watches(tuple(subscriptions))


def wait_for_observer_events(
    *,
    events_service: OperationsEventStreamPort,
    cursor_state: OperationsObserverCursorState,
    scan_state: OperationsObserverScanState,
    subscriptions: Sequence[OperationsObserverSubscription],
    timeout_seconds: float,
    stop_event: StopEvent,
) -> None:
    watches = build_observer_wait_watches(
        cursor_state=cursor_state,
        subscriptions=subscriptions,
    )
    if not watches:
        stop_event.wait(timeout_seconds)
        return
    triggered = events_service.wait_for_event_topics(
        watches,
        timeout_seconds=timeout_seconds,
        stop_event=stop_event,
    )
    if triggered is not None:
        scan_state.wakeup(triggered.topic)
