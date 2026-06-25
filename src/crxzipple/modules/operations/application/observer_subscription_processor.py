from __future__ import annotations

from crxzipple.core.logger import get_logger
from crxzipple.modules.operations.application.observer_cursor_state import (
    OperationsObserverCursorState,
)
from crxzipple.modules.operations.application.observer_subscriptions import (
    OperationsObserverSubscription,
)
from crxzipple.modules.operations.application.ports import OperationsEventStreamPort

logger = get_logger(__name__)


def process_observer_subscription(
    *,
    events_service: OperationsEventStreamPort,
    cursor_state: OperationsObserverCursorState,
    subscription: OperationsObserverSubscription,
    limit: int = 100,
    from_beginning: bool = False,
) -> int:
    cursor = cursor_state.cursor(subscription)
    records = events_service.read_event_topic(
        subscription.source_topic,
        after_cursor=(None if from_beginning else cursor),
        limit=max(int(limit), 1),
    )
    if records and subscription.batch_handler is not None:
        return _process_batch_records(
            events_service=events_service,
            cursor_state=cursor_state,
            subscription=subscription,
            records=records,
        )
    return _process_individual_records(
        events_service=events_service,
        cursor_state=cursor_state,
        subscription=subscription,
        records=records,
    )


def _process_batch_records(
    *,
    events_service: OperationsEventStreamPort,
    cursor_state: OperationsObserverCursorState,
    subscription: OperationsObserverSubscription,
    records: tuple[object, ...],
) -> int:
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
    _persist_cursor(
        events_service=events_service,
        cursor_state=cursor_state,
        subscription=subscription,
        cursor=records[-1].cursor,
    )
    return len(records)


def _process_individual_records(
    *,
    events_service: OperationsEventStreamPort,
    cursor_state: OperationsObserverCursorState,
    subscription: OperationsObserverSubscription,
    records: tuple[object, ...],
) -> int:
    processed_count = 0
    last_cursor: str | None = None
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
        _persist_cursor(
            events_service=events_service,
            cursor_state=cursor_state,
            subscription=subscription,
            cursor=last_cursor,
        )
    return processed_count


def _persist_cursor(
    *,
    events_service: OperationsEventStreamPort,
    cursor_state: OperationsObserverCursorState,
    subscription: OperationsObserverSubscription,
    cursor: str,
) -> None:
    events_service.set_subscription_cursor(
        subscription.subscription_id,
        source_topic=subscription.source_topic,
        cursor=cursor,
    )
    cursor_state.set_cursor(subscription, cursor)
