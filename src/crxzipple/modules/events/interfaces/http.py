from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.events import (
    EventSubscriptionCursor,
    EventTopicRecord,
    EventTopicWatch,
)
from crxzipple.shared import EventDefinitionRegistry


router = APIRouter()
_STUCK_SUBSCRIPTION_AFTER_SECONDS = 15.0
_CONSOLE_TOPIC_DISCOVERY_INTERVAL_SECONDS = 0.25


@dataclass(frozen=True, slots=True)
class EventConsoleStreamFilters:
    owner: str | None = None
    surface_id: str | None = None
    event_name: str | None = None
    topic_prefix: str | None = None
    run_id: str | None = None
    session_key: str | None = None
    interaction_id: str | None = None
    channel_type: str | None = None
    payload_key: str | None = None
    payload_value: str | None = None

    @classmethod
    def from_query(
        cls,
        *,
        owner: str | None = None,
        surface_id: str | None = None,
        event_name: str | None = None,
        topic_prefix: str | None = None,
        run_id: str | None = None,
        session_key: str | None = None,
        interaction_id: str | None = None,
        channel_type: str | None = None,
        payload_key: str | None = None,
        payload_value: str | None = None,
    ) -> EventConsoleStreamFilters:
        return cls(
            owner=_normalize_optional_text(owner),
            surface_id=_normalize_optional_text(surface_id),
            event_name=_normalize_optional_text(event_name),
            topic_prefix=_normalize_optional_text(topic_prefix),
            run_id=_normalize_optional_text(run_id),
            session_key=_normalize_optional_text(session_key),
            interaction_id=_normalize_optional_text(interaction_id),
            channel_type=_normalize_optional_text(channel_type),
            payload_key=_normalize_optional_text(payload_key),
            payload_value=_normalize_optional_text(payload_value),
        )

    def active(self) -> bool:
        return any(value is not None for value in self.to_payload().values())

    def to_payload(self) -> dict[str, str]:
        payload: dict[str, str] = {}
        for key, value in (
            ("owner", self.owner),
            ("surface_id", self.surface_id),
            ("event_name", self.event_name),
            ("topic_prefix", self.topic_prefix),
            ("run_id", self.run_id),
            ("session_key", self.session_key),
            ("interaction_id", self.interaction_id),
            ("channel_type", self.channel_type),
            ("payload_key", self.payload_key),
            ("payload_value", self.payload_value),
        ):
            if value is not None:
                payload[key] = value
        return payload


@router.get("/contracts")
def list_event_contracts(
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    payload = container.require(AppKey.EVENT_CONTRACT_REGISTRY).to_payload()
    payload.update(container.require(AppKey.EVENT_DEFINITION_REGISTRY).to_payload())
    return payload


@router.get("/stream")
def stream_event_console(
    container: Annotated[AppContainer, Depends(get_container)],
    snapshot_limit: Annotated[int, Query(ge=0, le=50)] = 20,
    timeout_seconds: Annotated[float, Query(gt=0.0, le=300.0)] = 120.0,
    owner: str | None = Query(default=None),
    surface_id: str | None = Query(default=None),
    event_name: str | None = Query(default=None),
    topic_prefix: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
    session_key: str | None = Query(default=None),
    interaction_id: str | None = Query(default=None),
    channel_type: str | None = Query(default=None),
    payload_key: str | None = Query(default=None),
    payload_value: str | None = Query(default=None),
) -> StreamingResponse:
    events_service = container.require(AppKey.EVENTS_SERVICE)
    if events_service is None:
        raise HTTPException(status_code=503, detail="Event service is not available.")

    filters = EventConsoleStreamFilters.from_query(
        owner=owner,
        surface_id=surface_id,
        event_name=event_name,
        topic_prefix=topic_prefix,
        run_id=run_id,
        session_key=session_key,
        interaction_id=interaction_id,
        channel_type=channel_type,
        payload_key=payload_key,
        payload_value=payload_value,
    )
    definition_registry = container.require(AppKey.EVENT_DEFINITION_REGISTRY)

    def event_stream():
        topic_cursors = _snapshot_console_topics(
            events_service=events_service,
            filters=filters,
        )
        yield _format_sse_event(
            "connected",
            {
                "topic": None,
                "latest_cursor": None,
                "topic_count": len(topic_cursors),
                "stream_role": "primary",
                "stream_scope": "bus",
                "filters": filters.to_payload(),
            },
        )
        if snapshot_limit > 0:
            snapshot_records = _read_recent_console_records(
                events_service=events_service,
                topic_cursors=topic_cursors,
                limit=snapshot_limit,
                definition_registry=definition_registry,
                filters=filters,
            )
        else:
            snapshot_records = ()
        yield _format_sse_event(
            "snapshot",
            {
                "topic": None,
                "latest_cursor": None,
                "topic_count": len(topic_cursors),
                "filters": filters.to_payload(),
                "records": list(snapshot_records),
            },
        )

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            topic_cursors = _refresh_console_topics(
                events_service=events_service,
                existing_cursors=topic_cursors,
                filters=filters,
            )
            emitted = False
            for topic, after_cursor in topic_cursors.items():
                records = events_service.read_event_topic(
                    topic,
                    after_cursor=after_cursor,
                    limit=100,
                )
                if not records:
                    continue
                topic_cursors[topic] = records[-1].cursor
                emitted = True
                for record in _sort_console_records(records):
                    summary = _console_topic_record_summary(
                        record,
                        definition_registry=definition_registry,
                    )
                    if not _matches_console_stream_filters(summary, filters):
                        continue
                    yield _format_sse_event("event", summary)
            if emitted:
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            wait_timeout = min(
                remaining,
                _CONSOLE_TOPIC_DISCOVERY_INTERVAL_SECONDS,
            )
            wait_items = tuple(
                EventTopicWatch(topic=topic, after_cursor=cursor)
                for topic, cursor in topic_cursors.items()
            )
            if not wait_items:
                time.sleep(min(wait_timeout, 0.1))
                continue
            events_service.wait_for_event_topics(
                wait_items,
                timeout_seconds=wait_timeout,
            )
        yield _format_sse_event(
            "timeout",
            {
                "topic": None,
                "latest_cursor": None,
                "topic_count": len(topic_cursors),
                "filters": filters.to_payload(),
            },
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Crx-Stream-Role": "primary",
            "X-Crx-Stream-Scope": "bus",
        },
    )


@router.get("/records")
def list_event_records(
    container: Annotated[AppContainer, Depends(get_container)],
    limit: Annotated[int, Query(ge=0, le=500)] = 50,
    owner: str | None = Query(default=None),
    surface_id: str | None = Query(default=None),
    event_name: str | None = Query(default=None),
    topic_prefix: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
    session_key: str | None = Query(default=None),
    interaction_id: str | None = Query(default=None),
    channel_type: str | None = Query(default=None),
    payload_key: str | None = Query(default=None),
    payload_value: str | None = Query(default=None),
) -> dict[str, Any]:
    events_service = container.require(AppKey.EVENTS_SERVICE)
    if events_service is None:
        raise HTTPException(status_code=503, detail="Event service is not available.")

    filters = EventConsoleStreamFilters.from_query(
        owner=owner,
        surface_id=surface_id,
        event_name=event_name,
        topic_prefix=topic_prefix,
        run_id=run_id,
        session_key=session_key,
        interaction_id=interaction_id,
        channel_type=channel_type,
        payload_key=payload_key,
        payload_value=payload_value,
    )
    topic_cursors = _snapshot_console_topics(
        events_service=events_service,
        filters=filters,
    )
    records = _read_recent_console_records(
        events_service=events_service,
        topic_cursors=topic_cursors,
        limit=limit,
        definition_registry=container.require(AppKey.EVENT_DEFINITION_REGISTRY),
        filters=filters,
    )
    return {
        "filters": filters.to_payload(),
        "topic_count": len(topic_cursors),
        "records": list(records),
    }


@router.get("/topics/{topic}/diagnostics")
def get_event_topic_diagnostics(
    topic: str,
    container: Annotated[AppContainer, Depends(get_container)],
    record_limit: Annotated[int, Query(ge=0, le=25)] = 5,
) -> dict[str, Any]:
    events_service = container.require(AppKey.EVENTS_SERVICE)
    if events_service is None:
        raise HTTPException(status_code=503, detail="Event service is not available.")
    normalized_topic = topic.strip()
    if not normalized_topic:
        raise HTTPException(status_code=400, detail="topic is required.")

    registry = container.require(AppKey.EVENT_CONTRACT_REGISTRY)
    latest_cursor = events_service.snapshot_event_topic(normalized_topic)
    subscription_cursors = events_service.list_subscription_cursors(
        source_topic=normalized_topic,
    )
    records = (
        events_service.read_event_topic(normalized_topic, limit=record_limit)
        if record_limit > 0
        else ()
    )
    subscription_payloads = [
        _topic_subscription_cursor_summary(
            state,
            latest_cursor=latest_cursor,
        )
        for state in subscription_cursors
    ]
    return {
        "topic": normalized_topic,
        "latest_cursor": latest_cursor,
        "contract_matches": [
            match.to_payload()
            for match in registry.match_topic_contracts(normalized_topic)
        ],
        "routes_as_source": [
            match.to_payload()
            for match in registry.match_route_contracts(
                normalized_topic,
                direction="source",
            )
        ],
        "routes_as_target": [
            match.to_payload()
            for match in registry.match_route_contracts(
                normalized_topic,
                direction="target",
            )
        ],
        "consumer_summary": _topic_consumer_summary(
            latest_cursor=latest_cursor,
            subscription_payloads=subscription_payloads,
        ),
        "subscription_cursors": subscription_payloads,
        "records": [_topic_record_summary(record) for record in records],
    }


@router.get("/subscriptions/diagnostics")
def list_event_subscription_diagnostics(
    container: Annotated[AppContainer, Depends(get_container)],
    source_topic_prefix: str | None = Query(default=None),
    subscription_prefix: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> dict[str, Any]:
    events_service = container.require(AppKey.EVENTS_SERVICE)
    if events_service is None:
        raise HTTPException(status_code=503, detail="Event service is not available.")

    normalized_source_topic_prefix = _normalize_optional_text(source_topic_prefix)
    normalized_subscription_prefix = _normalize_optional_text(subscription_prefix)
    normalized_status = _normalize_subscription_status(status)

    registry = container.require(AppKey.EVENT_CONTRACT_REGISTRY)
    all_states = events_service.list_subscription_cursors()
    filtered_states = tuple(
        state
        for state in all_states
        if (
            normalized_source_topic_prefix is None
            or state.source_topic.startswith(normalized_source_topic_prefix)
        )
        and (
            normalized_subscription_prefix is None
            or state.subscription_id.startswith(normalized_subscription_prefix)
        )
    )
    latest_cursors = {
        topic: events_service.snapshot_event_topic(topic)
        for topic in {state.source_topic for state in filtered_states}
    }
    items = [
        _subscription_diagnostic_item(
            state,
            latest_cursor=latest_cursors[state.source_topic],
            registry=registry,
        )
        for state in filtered_states
    ]
    if normalized_status is not None:
        items = [
            item
            for item in items
            if _matches_subscription_status_filter(
                item,
                status=normalized_status,
            )
        ]
    items.sort(
        key=lambda item: (
            not bool(item.get("stuck")),
            not bool(item.get("lagging")),
            bool(item.get("at_head")),
            -float(item.get("seconds_since_update") or 0.0),
            str(item.get("source_topic") or ""),
            str(item.get("subscription_id") or ""),
        ),
    )
    visible_items = items[:limit]
    return {
        "filters": {
            "source_topic_prefix": normalized_source_topic_prefix,
            "subscription_prefix": normalized_subscription_prefix,
            "status": normalized_status,
            "limit": limit,
        },
        "summary": _subscription_diagnostics_summary(
            total_count=len(all_states),
            visible_items=visible_items,
        ),
        "items": visible_items,
    }


def _topic_record_summary(record: EventTopicRecord) -> dict[str, Any]:
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


def _subscription_diagnostic_item(
    state: EventSubscriptionCursor,
    *,
    latest_cursor: str,
    registry,
) -> dict[str, Any]:
    payload = _topic_subscription_cursor_summary(state, latest_cursor=latest_cursor)
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


def _topic_subscription_cursor_summary(
    state: EventSubscriptionCursor,
    *,
    latest_cursor: str,
) -> dict[str, Any]:
    at_head = _compare_event_cursors(state.cursor, latest_cursor) >= 0
    lagging = not at_head
    seconds_since_update = max(
        0.0,
        (
            datetime.now(timezone.utc) - state.updated_at.astimezone(timezone.utc)
        ).total_seconds(),
    )
    stuck = lagging and seconds_since_update >= _STUCK_SUBSCRIPTION_AFTER_SECONDS
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


def _topic_consumer_summary(
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
        "stuck_after_seconds": _STUCK_SUBSCRIPTION_AFTER_SECONDS,
    }


def _subscription_diagnostics_summary(
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
        "stuck_after_seconds": _STUCK_SUBSCRIPTION_AFTER_SECONDS,
    }


def _console_topic_record_summary(
    record: EventTopicRecord,
    *,
    definition_registry: EventDefinitionRegistry,
) -> dict[str, Any]:
    payload = dict(record.envelope.payload)
    resolved_event_name = str(record.envelope.event_name or "").strip()
    definition = definition_registry.get_by_event_name(resolved_event_name)
    surfaces = definition_registry.list_surfaces_for_event_name(resolved_event_name)
    return {
        "cursor": record.cursor,
        "event_id": record.envelope.id,
        "event_name": record.envelope.event_name or "",
        "topic": record.envelope.topic,
        "kind": record.envelope.kind,
        "source_event_id": record.envelope.id,
        "source_event_name": record.envelope.event_name or "",
        "source_event_owner": definition.owner if definition is not None else None,
        "source_surface_ids": [surface.surface_id for surface in surfaces],
        "source_durability": definition.durability if definition is not None else None,
        "source_publication_mode": (
            definition.publication_mode if definition is not None else None
        ),
        "source_source_event_names": (
            list(definition.source_event_names)
            if definition is not None
            else []
        ),
        "source_topic": record.envelope.topic,
        "source_kind": record.envelope.kind,
        "source_payload": payload,
        "source_target": (
            record.envelope.target.to_payload()
            if record.envelope.target is not None
            else None
        ),
        "source_ordering_key": record.envelope.ordering_key,
        "source_dedupe_key": record.envelope.dedupe_key,
        "source_trace": dict(record.envelope.trace),
        "source_created_at": record.envelope.created_at.isoformat(),
        "created_at": record.envelope.created_at.isoformat(),
    }


def _read_recent_console_records(
    *,
    events_service,
    topic_cursors: dict[str, str | None],
    limit: int,
    definition_registry: EventDefinitionRegistry,
    filters: EventConsoleStreamFilters,
) -> tuple[dict[str, Any], ...]:
    if limit <= 0:
        return ()
    recent: list[dict[str, Any]] = []
    per_topic_limit = min(max(limit * 2, 10), 50)
    for topic, up_to_cursor in topic_cursors.items():
        records = events_service.read_recent_event_topic(
            topic,
            limit=per_topic_limit,
        )
        for record in records:
            if (
                up_to_cursor is not None
                and _compare_event_cursors(record.cursor, up_to_cursor) > 0
            ):
                continue
            summary = _console_topic_record_summary(
                record,
                definition_registry=definition_registry,
            )
            if _matches_console_stream_filters(summary, filters):
                recent.append(summary)
    recent.sort(
        key=lambda item: (
            str(item.get("created_at") or ""),
            str(item.get("topic") or ""),
            str(item.get("event_id") or ""),
        ),
        reverse=True,
    )
    return tuple(recent[:limit])


def _snapshot_console_topics(
    *,
    events_service,
    filters: EventConsoleStreamFilters,
) -> dict[str, str | None]:
    topics = _list_console_topics(
        events_service=events_service,
        filters=filters,
    )
    return {
        topic: events_service.snapshot_event_topic(topic)
        for topic in topics
    }


def _refresh_console_topics(
    *,
    events_service,
    existing_cursors: dict[str, str | None],
    filters: EventConsoleStreamFilters,
) -> dict[str, str | None]:
    refreshed = dict(existing_cursors)
    for topic in _list_console_topics(
        events_service=events_service,
        filters=filters,
    ):
        refreshed.setdefault(topic, None)
    return refreshed


def _list_console_topics(
    *,
    events_service,
    filters: EventConsoleStreamFilters,
) -> tuple[str, ...]:
    topics = events_service.list_event_topics()
    if filters.topic_prefix is not None:
        topics = tuple(
            topic for topic in topics if topic.startswith(filters.topic_prefix)
        )
    return tuple(sorted(dict.fromkeys(topics)))


def _sort_console_records(
    records: tuple[EventTopicRecord, ...],
) -> tuple[EventTopicRecord, ...]:
    return tuple(
        sorted(
            records,
            key=lambda record: (
                record.envelope.created_at.isoformat(),
                record.envelope.topic or "",
                record.envelope.id,
            ),
        ),
    )


def _matches_console_stream_filters(
    summary: dict[str, Any],
    filters: EventConsoleStreamFilters,
) -> bool:
    if not filters.active():
        return True
    if (
        filters.owner is not None
        and str(summary.get("source_event_owner") or "").strip() != filters.owner
    ):
        return False
    if filters.surface_id is not None:
        surface_ids = list(summary.get("source_surface_ids") or [])
        if filters.surface_id not in surface_ids:
            return False
    if filters.event_name is not None:
        event_names = {
            str(summary.get("source_event_name") or "").strip(),
            str(summary.get("event_name") or "").strip(),
        }
        if filters.event_name not in event_names:
            return False
    if filters.topic_prefix is not None:
        topic_candidate = str(summary.get("source_topic") or summary.get("topic") or "")
        if not topic_candidate.startswith(filters.topic_prefix):
            return False
    source_payload = dict(summary.get("source_payload") or {})
    if (
        filters.run_id is not None
        and filters.run_id not in _collect_nested_scalar_values(
            source_payload,
            field_names={"run_id", "source_id"},
        )
    ):
        return False
    if (
        filters.session_key is not None
        and filters.session_key not in _collect_nested_scalar_values(
            source_payload,
            field_names={"session_key"},
        )
    ):
        return False
    if (
        filters.interaction_id is not None
        and filters.interaction_id not in _collect_nested_scalar_values(
            source_payload,
            field_names={"interaction_id"},
        )
    ):
        return False
    if (
        filters.channel_type is not None
        and filters.channel_type not in _collect_nested_scalar_values(
            {
                "source_payload": source_payload,
                "source_target": dict(summary.get("source_target") or {}),
            },
            field_names={"channel_type", "transport"},
        )
    ):
        return False
    if filters.payload_key is not None:
        payload_value = _payload_lookup(source_payload, filters.payload_key)
        if filters.payload_value is None:
            if payload_value is None:
                return False
        elif not _payload_value_matches(payload_value, filters.payload_value):
            return False
    return True


def _collect_nested_scalar_values(
    payload: dict[str, Any],
    *,
    field_names: set[str],
) -> set[str]:
    values: set[str] = set()
    stack: list[Any] = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, value in current.items():
                if key in field_names and value is not None:
                    normalized = str(value).strip()
                    if normalized:
                        values.add(normalized)
                if isinstance(value, (dict, list, tuple)):
                    stack.append(value)
        elif isinstance(current, (list, tuple)):
            stack.extend(current)
    return values


def _payload_lookup(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        key = part.strip()
        if not key:
            return None
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _payload_value_matches(value: Any, expected: str) -> bool:
    if isinstance(value, (list, tuple, set)):
        return expected in {str(item).strip() for item in value if item is not None}
    if isinstance(value, dict):
        return False
    return str(value).strip() == expected


def _normalize_optional_text(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_subscription_status(value: str | None) -> str | None:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        return None
    if normalized not in {"at_head", "lagging", "stuck"}:
        raise HTTPException(
            status_code=400,
            detail="status must be one of: at_head, lagging, stuck.",
        )
    return normalized


def _matches_subscription_status_filter(
    item: dict[str, Any],
    *,
    status: str,
) -> bool:
    return bool(item.get(status))


def _format_sse_event(event_name: str, payload: dict[str, Any]) -> str:
    return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _compare_event_cursors(left: str | None, right: str | None) -> int:
    left_cursor = _parse_event_cursor(left)
    right_cursor = _parse_event_cursor(right)
    if left_cursor == right_cursor:
        return 0
    return 1 if left_cursor > right_cursor else -1


def _parse_event_cursor(cursor: str | None) -> tuple[int, int]:
    if not isinstance(cursor, str) or not cursor.strip():
        return (0, 0)
    if "-" not in cursor:
        try:
            return (int(cursor), 0)
        except ValueError:
            return (0, 0)
    left, right = cursor.split("-", 1)
    try:
        return (int(left), int(right))
    except ValueError:
        return (0, 0)
