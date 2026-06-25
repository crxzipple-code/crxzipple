from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.events.domain import EventCursor
from crxzipple.modules.operations.application.action_results import (
    EventSubscriptionAdvanceItem,
    EventSubscriptionAdvanceResult,
)
from crxzipple.shared.time import coerce_utc_datetime

DEFAULT_STUCK_SUBSCRIPTION_AFTER_SECONDS = 15.0


def advance_event_subscriptions_to_head(
    events_service: Any,
    *,
    subscription_id: str | None = None,
    source_topic: str | None = None,
    status: str = "stuck",
    observer_only: bool = False,
    stuck_after_seconds: float = DEFAULT_STUCK_SUBSCRIPTION_AFTER_SECONDS,
    dry_run: bool = False,
    reason: str | None = None,
) -> EventSubscriptionAdvanceResult:
    normalized_subscription_id = _optional_text(subscription_id)
    normalized_source_topic = _optional_text(source_topic)
    normalized_status = _normalize_status_filter(status)
    states = events_service.list_subscription_cursors(
        source_topic=normalized_source_topic,
    )
    now = datetime.now(timezone.utc)
    items: list[EventSubscriptionAdvanceItem] = []
    advanced_count = 0
    skipped_count = 0

    for state in states:
        if (
            normalized_subscription_id is not None
            and state.subscription_id != normalized_subscription_id
        ):
            continue
        if observer_only and not state.subscription_id.startswith("operations.observer."):
            continue
        latest_cursor = events_service.snapshot_event_topic(state.source_topic)
        state_status = _subscription_status(
            state.cursor,
            latest_cursor,
            updated_at=getattr(state, "updated_at", None),
            now=now,
            stuck_after_seconds=stuck_after_seconds,
        )
        if not _status_matches(state_status, normalized_status):
            skipped_count += 1
            continue
        changed = _compare_cursors(state.cursor, latest_cursor) < 0
        if changed and not dry_run:
            events_service.set_subscription_cursor(
                state.subscription_id,
                source_topic=state.source_topic,
                cursor=latest_cursor,
            )
            advanced_count += 1
        elif changed:
            advanced_count += 1
        else:
            skipped_count += 1
        items.append(
            EventSubscriptionAdvanceItem(
                subscription_id=state.subscription_id,
                source_topic=state.source_topic,
                previous_cursor=state.cursor,
                latest_cursor=latest_cursor,
                status=state_status,
                changed=changed,
            )
        )

    return EventSubscriptionAdvanceResult(
        matched_count=len(items),
        advanced_count=advanced_count,
        skipped_count=skipped_count,
        dry_run=dry_run,
        reason=_optional_text(reason),
        items=tuple(items),
    )


def _optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_status_filter(value: str | None) -> str:
    normalized = str(value or "stuck").strip().lower().replace("-", "_")
    if normalized not in {"all", "lagging", "stuck"}:
        return "stuck"
    return normalized


def _status_matches(status: str, filter_value: str) -> bool:
    if filter_value == "all":
        return True
    if filter_value == "lagging":
        return status in {"lagging", "stuck"}
    return status == "stuck"


def _subscription_status(
    cursor: EventCursor,
    latest_cursor: EventCursor,
    *,
    updated_at: Any,
    now: datetime,
    stuck_after_seconds: float,
) -> str:
    if _compare_cursors(cursor, latest_cursor) >= 0:
        return "at_head"
    if _seconds_since(updated_at, now=now) >= max(float(stuck_after_seconds), 0.0):
        return "stuck"
    return "lagging"


def _compare_cursors(left: str | None, right: str | None) -> int:
    left_cursor = _parse_cursor(left)
    right_cursor = _parse_cursor(right)
    if left_cursor == right_cursor:
        return 0
    return 1 if left_cursor > right_cursor else -1


def _parse_cursor(cursor: str | None) -> tuple[int, int]:
    raw = (cursor or "0-0").strip()
    if "-" not in raw:
        try:
            return (max(int(raw), 0), 0)
        except ValueError:
            return (0, 0)
    left, right = raw.split("-", 1)
    try:
        return (max(int(left), 0), max(int(right), 0))
    except ValueError:
        return (0, 0)


def _seconds_since(value: Any, *, now: datetime) -> float:
    if value is None:
        return float("inf")
    try:
        resolved = coerce_utc_datetime(value)
    except (TypeError, ValueError):
        return float("inf")
    return max(0.0, (now - resolved).total_seconds())
