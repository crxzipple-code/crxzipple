from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.events import EventSubscriptionCursor, EventTopicRecord
from crxzipple.modules.events.interfaces.http_console import compare_event_cursors


STUCK_SUBSCRIPTION_AFTER_SECONDS = 15.0


def topic_record_summary(record: EventTopicRecord) -> dict[str, Any]:
    envelope = record.envelope
    return {
        "cursor": record.cursor,
        "event_id": envelope.id,
        "kind": envelope.kind,
        "event_name": envelope.event_name,
        "created_at": envelope.occurred_at.isoformat(),
        "ordering_key": envelope.ordering_key,
        "dedupe_key": envelope.dedupe_key,
        "target": envelope.target.to_payload() if envelope.target is not None else None,
    }


def subscription_diagnostic_item(
    state: EventSubscriptionCursor,
    *,
    latest_cursor: str,
    registry,
) -> dict[str, Any]:
    payload = topic_subscription_cursor_summary(state, latest_cursor=latest_cursor)
    payload.update(
        {
            "latest_cursor": latest_cursor,
            "contract_matches": [
                match.to_payload()
                for match in registry.match_topic_contracts(state.source_topic)
            ],
            "routes_as_source": [
                match.to_payload()
                for match in registry.match_route_contracts(
                    state.source_topic,
                    direction="source",
                )
            ],
            "routes_as_target": [
                match.to_payload()
                for match in registry.match_route_contracts(
                    state.source_topic,
                    direction="target",
                )
            ],
        }
    )
    return payload


def topic_subscription_cursor_summary(
    state: EventSubscriptionCursor,
    *,
    latest_cursor: str,
) -> dict[str, Any]:
    at_head = compare_event_cursors(state.cursor, latest_cursor) >= 0
    lagging = not at_head
    seconds_since_update = max(
        0.0,
        (
            datetime.now(timezone.utc) - state.updated_at.astimezone(timezone.utc)
        ).total_seconds(),
    )
    stuck = lagging and seconds_since_update >= STUCK_SUBSCRIPTION_AFTER_SECONDS
    payload = state.to_payload()
    payload.update(
        {
            "at_head": at_head,
            "lagging": lagging,
            "stuck": stuck,
            "seconds_since_update": round(seconds_since_update, 3),
        }
    )
    return payload


def topic_consumer_summary(
    *,
    latest_cursor: str,
    subscription_payloads: list[dict[str, Any]],
) -> dict[str, Any]:
    total_count = len(subscription_payloads)
    at_head_count = sum(1 for item in subscription_payloads if bool(item.get("at_head")))
    lagging_count = sum(1 for item in subscription_payloads if bool(item.get("lagging")))
    stuck_count = sum(1 for item in subscription_payloads if bool(item.get("stuck")))
    return {
        "latest_cursor": latest_cursor,
        "total_count": total_count,
        "at_head_count": at_head_count,
        "lagging_count": lagging_count,
        "stuck_count": stuck_count,
        "stuck_after_seconds": STUCK_SUBSCRIPTION_AFTER_SECONDS,
    }


def subscription_diagnostics_summary(
    *,
    total_count: int,
    visible_items: list[dict[str, Any]],
) -> dict[str, Any]:
    visible_count = len(visible_items)
    source_topic_count = len(
        {
            str(item.get("source_topic") or "").strip()
            for item in visible_items
            if str(item.get("source_topic") or "").strip()
        }
    )
    at_head_count = sum(1 for item in visible_items if bool(item.get("at_head")))
    lagging_count = sum(1 for item in visible_items if bool(item.get("lagging")))
    stuck_count = sum(1 for item in visible_items if bool(item.get("stuck")))
    return {
        "total_count": total_count,
        "visible_count": visible_count,
        "source_topic_count": source_topic_count,
        "at_head_count": at_head_count,
        "lagging_count": lagging_count,
        "stuck_count": stuck_count,
        "stuck_after_seconds": STUCK_SUBSCRIPTION_AFTER_SECONDS,
    }


def matches_subscription_status_filter(
    item: dict[str, Any],
    *,
    status: str,
) -> bool:
    return bool(item.get(status))
