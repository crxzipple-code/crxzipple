from __future__ import annotations

import json
import time
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.modules.channels.domain import (
    channel_broadcast_topic,
    channel_connection_control_topic,
)
from crxzipple.modules.events import EventAddress, EventTopicWatch
from crxzipple.modules.orchestration.application import (
    turn_session_live_topic,
    turn_session_topic,
)


router = APIRouter()


class WebChannelConnectedEventResponse(BaseModel):
    runtime_id: str
    service_key: str | None = None
    channel_account_id: str
    connection_id: str
    conversation_id: str | None = None
    supports_streaming: bool
    stream_role: str = "primary"
    observe_mode: str = "preferred"
    metadata: dict[str, Any] = Field(default_factory=dict)


class WebChannelBroadcastEventResponse(BaseModel):
    event_id: str
    topic: str
    payload: dict[str, Any] = Field(default_factory=dict)
    target: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class WebChannelObserveEventResponse(BaseModel):
    event_id: str
    event_name: str
    topic: str
    source_topic: str | None = None
    source_cursor: str | None = None
    fact: dict[str, Any] = Field(default_factory=dict)
    target: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class WebChannelLiveEventResponse(BaseModel):
    event_id: str
    event_name: str
    topic: str
    source_topic: str | None = None
    source_cursor: str | None = None
    live: dict[str, Any] = Field(default_factory=dict)
    target: dict[str, Any] = Field(default_factory=dict)
    created_at: str


def _format_sse_event(event_name: str, payload: dict[str, object]) -> str:
    return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _build_direct_live_event_response(
    *,
    record: Any,
    runtime_id: str,
    service_key: str | None,
    web_channel_account_id: str,
    web_connection_id: str,
    conversation_id: str | None,
) -> WebChannelLiveEventResponse | None:
    live_payload = dict(record.envelope.payload or {})
    event_name = record.envelope.event_name or ""
    if not event_name:
        return None
    target = EventAddress(
        address=web_connection_id,
        address_kind="connection",
        runtime=runtime_id,
        transport="web",
        account=web_channel_account_id,
        conversation=conversation_id,
        connection=web_connection_id,
        metadata={
            "path": "direct_source",
            "service_key": service_key,
            "source_topic": record.envelope.topic,
            "source_cursor": record.cursor,
        },
    )
    return WebChannelLiveEventResponse(
        event_id=record.envelope.id,
        event_name=event_name,
        topic=record.envelope.topic,
        source_topic=record.envelope.topic,
        source_cursor=record.cursor,
        live=live_payload,
        target=target.to_payload(),
        created_at=record.envelope.created_at.isoformat(),
    )


def _build_direct_observe_event_response(
    *,
    record: Any,
    runtime_id: str,
    service_key: str | None,
    web_channel_account_id: str,
    web_connection_id: str,
    conversation_id: str | None,
) -> WebChannelObserveEventResponse | None:
    fact_payload = dict(record.envelope.payload or {})
    event_name = record.envelope.event_name or ""
    if not event_name:
        return None
    target = EventAddress(
        address=web_connection_id,
        address_kind="connection",
        runtime=runtime_id,
        transport="web",
        account=web_channel_account_id,
        conversation=conversation_id,
        connection=web_connection_id,
        metadata={
            "path": "direct_source",
            "service_key": service_key,
            "source_topic": record.envelope.topic,
            "source_cursor": record.cursor,
        },
    )
    return WebChannelObserveEventResponse(
        event_id=record.envelope.id,
        event_name=event_name,
        topic=record.envelope.topic,
        source_topic=record.envelope.topic,
        source_cursor=record.cursor,
        fact=fact_payload,
        target=target.to_payload(),
        created_at=record.envelope.created_at.isoformat(),
    )


def _broadcast_target_matches_connection(
    *,
    target: EventAddress | None,
    connection_id: str,
    channel_account_id: str,
    conversation_id: str | None,
) -> bool:
    if target is None:
        return True
    if target.channel_type not in {None, "web"}:
        return False
    if target.connection_id:
        return target.connection_id == connection_id
    if target.channel_account_id and target.channel_account_id != channel_account_id:
        return False
    if target.conversation_id:
        return target.conversation_id == conversation_id
    return True


@router.get("/web/events")
def stream_web_channel_events(
    container: Annotated[AppContainer, Depends(get_container)],
    timeout_seconds: Annotated[float, Query(gt=0.0, le=300.0)] = 30.0,
    channel_account_id: str | None = Query(default=None),
    connection_id: str | None = Query(default=None),
    conversation_id: str | None = Query(default=None),
) -> StreamingResponse:
    events_service = container.require(AppKey.EVENTS_SERVICE)
    web_channel_account_id = (
        channel_account_id.strip()
        if isinstance(channel_account_id, str) and channel_account_id.strip()
        else "default"
    )
    web_connection_id = (
        connection_id.strip()
        if isinstance(connection_id, str) and connection_id.strip()
        else f"web-channel-{uuid4().hex}"
    )
    normalized_conversation_id = (
        conversation_id.strip()
        if isinstance(conversation_id, str) and conversation_id.strip()
        else None
    )
    existing_binding = container.require(AppKey.CHANNEL_RUNTIME_MANAGER).resolve_connection_binding(
        channel_type="web",
        connection_id=web_connection_id,
    )
    connection_binding = container.require(AppKey.WEB_CHANNEL_RUNTIME_SERVICE).bind_connection(
        connection_id=web_connection_id,
        channel_account_id=(
            existing_binding.channel_account_id
            if existing_binding is not None
            else web_channel_account_id
        ),
        conversation_id=(
            existing_binding.conversation_id
            if existing_binding is not None
            else normalized_conversation_id
        ),
        supports_streaming=True,
        runtime_id=(
            existing_binding.runtime_id
            if existing_binding is not None
            else "web-runtime-1"
        ),
        metadata={
            **(
                dict(existing_binding.metadata)
                if existing_binding is not None
                else {}
            ),
        },
    )
    if connection_binding.conversation_id:
        connection_binding = (
            container.require(AppKey.WEB_CHANNEL_RUNTIME_SERVICE).ensure_connection_source_cursors(
                connection_id=connection_binding.connection_id,
                conversation_id=connection_binding.conversation_id,
            )
            or connection_binding
        )
    runtime = container.require(AppKey.CHANNEL_RUNTIME_MANAGER).get_runtime(connection_binding.runtime_id)
    broadcast_topics = tuple(
        dict.fromkeys(
            (
                channel_broadcast_topic("web"),
                channel_broadcast_topic(
                    "web",
                    channel_account_id=web_channel_account_id,
                ),
            ),
        ),
    )
    control_topic = channel_connection_control_topic(
        "web",
        connection_id=web_connection_id,
    )

    def event_stream():
        try:
            deadline = time.monotonic() + timeout_seconds
            broadcast_cursors = {
                topic: events_service.snapshot_event_topic(topic)
                for topic in broadcast_topics
            }
            control_cursor = events_service.snapshot_event_topic(control_topic)

            connected_event = WebChannelConnectedEventResponse(
                runtime_id=connection_binding.runtime_id,
                service_key=runtime.service_key if runtime is not None else None,
                channel_account_id=web_channel_account_id,
                connection_id=web_connection_id,
                conversation_id=connection_binding.conversation_id,
                supports_streaming=connection_binding.supports_streaming,
                metadata=dict(connection_binding.metadata),
            )
            yield _format_sse_event(
                "connected",
                connected_event.model_dump(mode="json"),
            )

            while time.monotonic() < deadline:
                latest_binding = container.require(AppKey.CHANNEL_RUNTIME_MANAGER).resolve_connection_binding(
                    channel_type="web",
                    connection_id=web_connection_id,
                )
                if latest_binding is not None:
                    connection_binding_ref = latest_binding
                else:
                    connection_binding_ref = connection_binding
                control_records = events_service.read_event_topic(
                    control_topic,
                    after_cursor=control_cursor,
                    limit=20,
                )
                if control_records:
                    control_cursor = control_records[-1].cursor
                direct_live_conversation_id = (
                    connection_binding_ref.conversation_id.strip()
                    if isinstance(connection_binding_ref.conversation_id, str)
                    and connection_binding_ref.conversation_id.strip()
                    else None
                )
                direct_live_topic = (
                    turn_session_live_topic(direct_live_conversation_id)
                    if direct_live_conversation_id is not None
                    else None
                )
                direct_observe_topic = (
                    turn_session_topic(direct_live_conversation_id)
                    if direct_live_conversation_id is not None
                    else None
                )
                if direct_observe_topic is not None:
                    direct_observe_records = (
                        container.require(AppKey.WEB_CHANNEL_RUNTIME_SERVICE).read_connection_observe_records(
                            connection_id=web_connection_id,
                            conversation_id=direct_live_conversation_id,
                            limit=100,
                        )
                    )
                    for record in direct_observe_records:
                        observe_event = _build_direct_observe_event_response(
                            record=record,
                            runtime_id=connection_binding_ref.runtime_id,
                            service_key=runtime.service_key if runtime is not None else None,
                            web_channel_account_id=web_channel_account_id,
                            web_connection_id=web_connection_id,
                            conversation_id=direct_live_conversation_id,
                        )
                        if observe_event is None:
                            continue
                        yield _format_sse_event(
                            "observe",
                            observe_event.model_dump(mode="json"),
                        )
                if direct_live_topic is not None:
                    direct_live_records = (
                        container.require(AppKey.WEB_CHANNEL_RUNTIME_SERVICE).read_connection_live_records(
                            connection_id=web_connection_id,
                            conversation_id=direct_live_conversation_id,
                            limit=1,
                        )
                    )
                    for record in direct_live_records:
                        live_event = _build_direct_live_event_response(
                            record=record,
                            runtime_id=connection_binding_ref.runtime_id,
                            service_key=runtime.service_key if runtime is not None else None,
                            web_channel_account_id=web_channel_account_id,
                            web_connection_id=web_connection_id,
                            conversation_id=direct_live_conversation_id,
                        )
                        if live_event is None:
                            continue
                        yield _format_sse_event(
                            "live",
                            live_event.model_dump(mode="json"),
                        )
                for topic in broadcast_topics:
                    records = events_service.read_event_topic(
                        topic,
                        after_cursor=broadcast_cursors.get(topic),
                        limit=100,
                    )
                    if records:
                        broadcast_cursors[topic] = records[-1].cursor
                    for record in records:
                        if not _broadcast_target_matches_connection(
                            target=record.envelope.target,
                            connection_id=web_connection_id,
                            channel_account_id=web_channel_account_id,
                            conversation_id=connection_binding_ref.conversation_id,
                        ):
                            continue
                        broadcast_event = WebChannelBroadcastEventResponse(
                            event_id=record.envelope.id,
                            topic=record.envelope.topic,
                            payload=dict(record.envelope.payload),
                            target=(
                                record.envelope.target.to_payload()
                                if record.envelope.target is not None
                                else {}
                            ),
                            created_at=record.envelope.created_at.isoformat(),
                        )
                        yield _format_sse_event(
                            "broadcast",
                            broadcast_event.model_dump(mode="json"),
                        )

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                wait_timeout = remaining
                wait_binding = (
                    container.require(AppKey.CHANNEL_RUNTIME_MANAGER).resolve_connection_binding(
                        channel_type="web",
                        connection_id=web_connection_id,
                    )
                    or connection_binding_ref
                )
                wait_items: list[EventTopicWatch] = []
                wait_conversation_id = (
                    wait_binding.conversation_id.strip()
                    if isinstance(wait_binding.conversation_id, str)
                    and wait_binding.conversation_id.strip()
                    else None
                )
                wait_items.extend(
                    container.require(AppKey.WEB_CHANNEL_RUNTIME_SERVICE).build_connection_wait_watches(
                        connection_id=web_connection_id,
                        conversation_id=wait_conversation_id,
                        broadcast_topics=broadcast_topics,
                        broadcast_cursors=broadcast_cursors,
                    )
                )
                wait_items.append(
                    EventTopicWatch(
                        topic=control_topic,
                        after_cursor=control_cursor,
                    )
                )
                events_service.wait_for_event_topics(
                    tuple(wait_items),
                    timeout_seconds=wait_timeout,
                )

            yield _format_sse_event(
                "timeout",
                {
                    "connection_id": web_connection_id,
                    "channel_account_id": web_channel_account_id,
                },
            )
        finally:
            container.require(AppKey.WEB_CHANNEL_RUNTIME_SERVICE).unbind_connection(web_connection_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Crx-Stream-Role": "primary",
            "X-Crx-Stream-Scope": "channel",
        },
    )
