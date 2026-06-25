from __future__ import annotations

from typing import Any

from crxzipple.modules.channels.application.payload_redaction import (
    redact_channel_payload,
)
from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.observation_event_projection import observed_event_from_record
from crxzipple.modules.operations.application.read_models.channels_event_helpers import (
    event_status,
)
from crxzipple.modules.operations.application.read_models.channels_formatting import (
    first_text,
    text,
)
from crxzipple.modules.operations.application.read_models.channels_models import (
    ChannelEventRecord,
)
from crxzipple.modules.operations.application.read_models.channels_topic_helpers import (
    channel_from_topic,
    connection_from_topic,
    runtime_from_topic,
)
from crxzipple.shared.time import coerce_utc_datetime


def channel_event_from_observed_event(
    observed: OperationsObservedEvent,
) -> ChannelEventRecord:
    payload = dict(observed.payload)
    topic = text(observed.topic, "") or text(observed.cursor, "")
    return ChannelEventRecord(
        id=observed.id,
        cursor=observed.cursor,
        topic=topic,
        event_name=observed.event_name,
        kind=observed.kind,
        status=event_status(observed, payload),
        occurred_at=coerce_utc_datetime(observed.occurred_at),
        channel_type=first_text(
            payload.get("channel_type"),
            payload.get("channel"),
            channel_from_topic(topic),
        ),
        runtime_id=first_text(payload.get("runtime_id"), runtime_from_topic(topic)),
        channel_account_id=first_text(
            payload.get("channel_account_id"),
            payload.get("account_id"),
        ),
        connection_id=first_text(
            payload.get("connection_id"),
            connection_from_topic(topic),
        ),
        conversation_id=first_text(
            payload.get("conversation_id"),
            payload.get("session_key"),
        ),
        run_id=observed.run_id,
        trace_id=observed.trace_id,
        payload=payload,
        trace={},
    )


def channel_event_from_record(
    record: Any,
    *,
    definition_registry: Any | None,
) -> ChannelEventRecord:
    observed = observed_event_from_record(
        record,
        definition_registry=definition_registry,
    )
    event = record.envelope
    payload = dict(event.payload) if isinstance(event.payload, dict) else {}
    trace = dict(getattr(event, "trace", {}) or {})
    target_payload = (
        event.target.to_payload() if getattr(event, "target", None) is not None else {}
    )
    topic = text(getattr(event, "topic", None), "") or text(getattr(record, "cursor", None), "")
    return ChannelEventRecord(
        id=text(getattr(event, "id", None), observed.id),
        cursor=text(getattr(record, "cursor", None), observed.cursor),
        topic=topic,
        event_name=observed.event_name,
        kind=text(getattr(event, "kind", None), observed.kind),
        status=event_status(observed, payload),
        occurred_at=coerce_utc_datetime(getattr(event, "occurred_at", observed.occurred_at)),
        channel_type=first_text(
            payload.get("channel_type"),
            payload.get("channel"),
            target_payload.get("transport"),
            target_payload.get("channel_type"),
            channel_from_topic(topic),
        ),
        runtime_id=first_text(
            payload.get("runtime_id"),
            target_payload.get("runtime"),
            target_payload.get("runtime_id"),
            runtime_from_topic(topic),
        ),
        channel_account_id=first_text(
            payload.get("channel_account_id"),
            payload.get("account_id"),
            target_payload.get("account"),
            target_payload.get("channel_account_id"),
        ),
        connection_id=first_text(
            payload.get("connection_id"),
            target_payload.get("connection"),
            target_payload.get("connection_id"),
            connection_from_topic(topic),
        ),
        conversation_id=first_text(
            payload.get("conversation_id"),
            payload.get("session_key"),
            target_payload.get("conversation"),
            target_payload.get("conversation_id"),
        ),
        run_id=first_text(payload.get("run_id"), observed.run_id),
        trace_id=first_text(trace.get("trace_id"), observed.trace_id),
        payload=redact_channel_payload(payload),
        trace=trace,
    )


def with_connection_binding(
    event: ChannelEventRecord,
    *,
    binding_by_conversation: dict[str, Any],
) -> ChannelEventRecord:
    if event.conversation_id is None:
        return event
    binding = binding_by_conversation.get(event.conversation_id)
    if binding is None:
        return event
    return ChannelEventRecord(
        id=event.id,
        cursor=event.cursor,
        topic=event.topic,
        event_name=event.event_name,
        kind=event.kind,
        status=event.status,
        occurred_at=event.occurred_at,
        channel_type=event.channel_type or text(getattr(binding, "channel_type", None), ""),
        runtime_id=event.runtime_id or text(getattr(binding, "runtime_id", None), ""),
        channel_account_id=event.channel_account_id
        or text(getattr(binding, "channel_account_id", None), ""),
        connection_id=event.connection_id or text(getattr(binding, "connection_id", None), ""),
        conversation_id=event.conversation_id,
        run_id=event.run_id,
        trace_id=event.trace_id,
        payload=event.payload,
        trace=event.trace,
    )
