from __future__ import annotations

import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.events import (
    EventTopicWatch,
)
from crxzipple.modules.events.interfaces.http_console import (
    EventConsoleStreamFilters,
    console_topic_record_summary,
    format_sse_event,
    matches_console_stream_filters,
    normalize_optional_text,
    read_recent_console_records,
    refresh_console_topics,
    snapshot_console_topics,
    sort_console_records,
)
from crxzipple.modules.events.interfaces.http_diagnostics import (
    matches_subscription_status_filter,
    subscription_diagnostic_item,
    subscription_diagnostics_summary,
    topic_consumer_summary,
    topic_record_summary,
    topic_subscription_cursor_summary,
)


router = APIRouter()
_CONSOLE_TOPIC_DISCOVERY_INTERVAL_SECONDS = 0.25


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
        topic_cursors = snapshot_console_topics(
            events_service=events_service,
            filters=filters,
        )
        yield format_sse_event(
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
            snapshot_records = read_recent_console_records(
                events_service=events_service,
                topic_cursors=topic_cursors,
                limit=snapshot_limit,
                definition_registry=definition_registry,
                filters=filters,
            )
        else:
            snapshot_records = ()
        yield format_sse_event(
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
            topic_cursors = refresh_console_topics(
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
                for record in sort_console_records(records):
                    summary = console_topic_record_summary(
                        record,
                        definition_registry=definition_registry,
                    )
                    if not matches_console_stream_filters(summary, filters):
                        continue
                    yield format_sse_event("event", summary)
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
        yield format_sse_event(
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
    topic_cursors = snapshot_console_topics(
        events_service=events_service,
        filters=filters,
    )
    records = read_recent_console_records(
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
        topic_subscription_cursor_summary(
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
        "consumer_summary": topic_consumer_summary(
            latest_cursor=latest_cursor,
            subscription_payloads=subscription_payloads,
        ),
        "subscription_cursors": subscription_payloads,
        "records": [topic_record_summary(record) for record in records],
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

    normalized_source_topic_prefix = normalize_optional_text(source_topic_prefix)
    normalized_subscription_prefix = normalize_optional_text(subscription_prefix)
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
        subscription_diagnostic_item(
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
            if matches_subscription_status_filter(
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
        "summary": subscription_diagnostics_summary(
            total_count=len(all_states),
            visible_items=visible_items,
        ),
        "items": visible_items,
    }


def _normalize_subscription_status(value: str | None) -> str | None:
    normalized = normalize_optional_text(value)
    if normalized is None:
        return None
    if normalized not in {"at_head", "lagging", "stuck"}:
        raise HTTPException(
            status_code=400,
            detail="status must be one of: at_head, lagging, stuck.",
        )
    return normalized
