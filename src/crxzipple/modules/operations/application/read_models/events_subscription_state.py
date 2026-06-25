from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.operations.application.read_models.events_contract_matching import (
    contract_ids,
    match_route_contracts,
    match_topic_contracts,
)
from crxzipple.modules.operations.application.read_models.events_state_common import (
    compare_event_cursors,
    cursor_gap,
    display,
    join,
    seconds_since_datetime,
)
from crxzipple.shared.time import format_datetime_utc

_STUCK_SUBSCRIPTION_AFTER_SECONDS = 15.0


def subscription_states(
    states: tuple[Any, ...],
    *,
    latest_cursors: dict[str, str | None],
    now: datetime,
    registry: Any | None,
) -> list[dict[str, Any]]:
    items = []
    for state in states:
        source_topic = display(getattr(state, "source_topic", None))
        items.append(
            _subscription_state_entry(
                subscription_id=display(getattr(state, "subscription_id", None)),
                source_topic=source_topic,
                cursor=display(getattr(state, "cursor", None)),
                latest_cursor=latest_cursors.get(source_topic),
                updated_at=getattr(state, "updated_at", None),
                now=now,
                registry=registry,
                observer_registered=False,
            )
        )
    return items


def observer_subscription_states(
    observer_subscriptions: tuple[Any, ...],
    *,
    subscription_cursors: tuple[Any, ...],
    latest_cursors: dict[str, str | None],
    now: datetime,
    registry: Any | None,
) -> list[dict[str, Any]]:
    states_by_subscription = {
        display(getattr(state, "subscription_id", None)): state
        for state in subscription_cursors
    }
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for subscription in observer_subscriptions:
        subscription_id = display(getattr(subscription, "subscription_id", None))
        if subscription_id == "-":
            continue
        state = states_by_subscription.get(subscription_id)
        source_topic = display(
            getattr(state, "source_topic", None)
            if state is not None
            else getattr(subscription, "source_topic", None)
        )
        items.append(
            _subscription_state_entry(
                subscription_id=subscription_id,
                source_topic=source_topic,
                cursor=(
                    display(getattr(state, "cursor", None))
                    if state is not None
                    else "-"
                ),
                latest_cursor=latest_cursors.get(source_topic),
                updated_at=(
                    getattr(state, "updated_at", None) if state is not None else None
                ),
                now=now,
                registry=registry,
                observer_registered=True,
            )
        )
        seen.add(subscription_id)

    for state in subscription_cursors:
        subscription_id = display(getattr(state, "subscription_id", None))
        if (
            subscription_id in seen
            or not _is_operations_observer_subscription_id(subscription_id)
        ):
            continue
        source_topic = display(getattr(state, "source_topic", None))
        items.append(
            _subscription_state_entry(
                subscription_id=subscription_id,
                source_topic=source_topic,
                cursor=display(getattr(state, "cursor", None)),
                latest_cursor=latest_cursors.get(source_topic),
                updated_at=getattr(state, "updated_at", None),
                now=now,
                registry=registry,
                observer_registered=False,
            )
        )
    return items


def safe_subscription_cursors(events_service: Any | None) -> tuple[Any, ...]:
    if events_service is None:
        return ()
    try:
        return tuple(events_service.list_subscription_cursors())
    except Exception:
        return ()


def safe_observer_subscriptions(runtime: Any | None) -> tuple[Any, ...]:
    if runtime is None:
        return ()
    try:
        subscriptions = getattr(runtime, "subscriptions", ())
    except Exception:
        return ()
    if callable(subscriptions):
        try:
            subscriptions = subscriptions()
        except Exception:
            return ()
    try:
        return tuple(subscriptions)
    except TypeError:
        return ()


def _subscription_state_entry(
    *,
    subscription_id: str,
    source_topic: str,
    cursor: str,
    latest_cursor: str | None,
    updated_at: Any,
    now: datetime,
    registry: Any | None,
    observer_registered: bool,
) -> dict[str, Any]:
    latest_cursor_label = display(latest_cursor)
    comparison = compare_event_cursors(cursor, latest_cursor_label)
    lagging = comparison < 0
    seconds_since_update = seconds_since_datetime(updated_at, now=now)
    stuck = lagging and seconds_since_update >= _STUCK_SUBSCRIPTION_AFTER_SECONDS
    contract_matches = match_topic_contracts(registry, source_topic)
    route_matches = match_route_contracts(registry, source_topic)
    return {
        "subscription_id": subscription_id,
        "source_topic": source_topic,
        "cursor": cursor,
        "latest_cursor": latest_cursor_label,
        "lag": cursor_gap(latest_cursor_label, cursor),
        "at_head": not lagging,
        "lagging": lagging,
        "stuck": stuck,
        "status": "Stuck" if stuck else "Lagging" if lagging else "At Head",
        "updated_at": (
            format_datetime_utc(updated_at.astimezone(timezone.utc))
            if isinstance(updated_at, datetime)
            else "-"
        ),
        "seconds_since_update": round(seconds_since_update, 3),
        "contract_label": join(contract_ids(contract_matches)),
        "route_label": join(contract_ids(route_matches)),
        "observer_registered": observer_registered,
    }


def _is_operations_observer_subscription_id(subscription_id: str) -> bool:
    return subscription_id.startswith("operations.observer.")
