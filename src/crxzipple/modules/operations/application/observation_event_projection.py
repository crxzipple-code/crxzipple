from __future__ import annotations

from typing import Any

from crxzipple.modules.events.domain import EventTopicRecord
from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.modules.operations.application.observation_payloads import (
    optional_text,
    sanitize_payload,
)
from crxzipple.shared.domain.events import Event, NAMED_EVENT_TOPIC_PREFIX
from crxzipple.shared.event_contracts import EventDefinitionRegistry
from crxzipple.shared.time import coerce_utc_datetime


def observed_event_from_record(
    record: EventTopicRecord,
    *,
    definition_registry: EventDefinitionRegistry | None = None,
) -> OperationsObservedEvent:
    event = record.envelope
    payload = dict(event.payload)
    event_name = event_name_from_event(event, payload)
    definition = (
        definition_registry.get_by_event_name(event_name)
        if definition_registry is not None
        else None
    )
    owner = definition.owner if definition is not None else owner_from_name(event_name)
    module = module_from_owner(owner, event_name)
    status = event_status(event_name, payload)
    trace_id = trace_id_from_event(event, payload)
    run_id = run_id_from_payload(payload)
    entity_id = entity_id_from_payload(payload, fallback=run_id or event.id or event_name)
    source_event_name = optional_text(payload.get("source_event_name"))
    return OperationsObservedEvent(
        id=event.id,
        cursor=record.cursor,
        topic=event.topic or record.cursor,
        event_name=event_name,
        module=module,
        owner=owner,
        kind=event.kind,
        level=event_level(event_name, status, payload),
        status=status,
        entity_id=entity_id,
        run_id=run_id,
        trace_id=trace_id,
        source_event_name=source_event_name,
        occurred_at=coerce_utc_datetime(event.occurred_at),
        payload=sanitize_payload(payload),
    )


def event_name_from_event(event: Event, payload: dict[str, Any]) -> str:
    if event.event_name:
        return normalize_event_name(event.event_name)
    payload_name = optional_text(payload.get("event_name"))
    if payload_name:
        return normalize_event_name(payload_name)
    if event.topic:
        return normalize_event_name(event.topic)
    return "event"


def normalize_event_name(value: str) -> str:
    normalized = value.strip()
    named_prefix = f"{NAMED_EVENT_TOPIC_PREFIX}."
    if normalized.startswith(named_prefix):
        return normalized[len(named_prefix):]
    return normalized


def owner_from_name(event_name: str) -> str:
    first = event_name.split(".", 1)[0].strip().lower()
    if first == "channel":
        return "channels"
    if first == "event_relay":
        return "events"
    return first or "system"


def module_from_owner(owner: str, event_name: str) -> str:
    normalized = owner.strip().lower().replace("_", "-")
    if normalized in {"channel", "channels"}:
        return "channels"
    if normalized in {"event", "events", "event-relay"}:
        return "events"
    if normalized:
        return normalized
    return owner_from_name(event_name)


def event_status(event_name: str, payload: dict[str, Any]) -> str:
    status = optional_text(payload.get("status"))
    if status:
        return status
    tail = event_name.rsplit(".", 1)[-1].strip().lower()
    return tail.replace("_", "-") or "observed"


def event_level(
    event_name: str,
    status: str,
    payload: dict[str, Any],
) -> str:
    explicit = optional_text(payload.get("level"))
    if explicit in {"debug", "info", "warning", "error"}:
        return explicit
    text = f"{event_name} {status}".lower()
    if any(token in text for token in ("failed", "error", "timed_out", "dead")):
        return "error"
    if any(token in text for token in ("cancelled", "stale", "offline", "warning")):
        return "warning"
    return "info"


def entity_id_from_payload(payload: dict[str, Any], *, fallback: str) -> str:
    for key in (
        "run_id",
        "owner_id",
        "request_id",
        "tool_run_id",
        "assignment_id",
        "worker_id",
        "llm_id",
        "invocation_id",
        "source_event_id",
        "connection_id",
        "runtime_id",
        "resource_id",
        "target_id",
        "binding_id",
        "credential_binding_id",
        "audit_ref",
    ):
        value = optional_text(payload.get(key))
        if value:
            return value
    return fallback


def run_id_from_payload(payload: dict[str, Any]) -> str | None:
    explicit = optional_text(payload.get("run_id"))
    if explicit:
        return explicit
    owner_kind = optional_text(payload.get("owner_kind"))
    if owner_kind == "orchestration_run":
        return optional_text(payload.get("owner_id"))
    return None


def trace_id_from_event(event: Event, payload: dict[str, Any]) -> str | None:
    for key in ("trace_id", "correlation_id", "source_event_id"):
        value = optional_text(payload.get(key))
        if value:
            return value
    for key in ("trace_id", "correlation_id"):
        value = optional_text(event.trace.get(key))
        if value:
            return value
    return None
