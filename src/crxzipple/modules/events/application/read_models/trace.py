from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from crxzipple.modules.events.application import EventsApplicationService
from crxzipple.modules.events.application.read_models.trace_topics import (
    per_topic_trace_limit,
    trace_source_topics,
)
from crxzipple.modules.events.domain import EventTopicRecord
from crxzipple.shared import EventDefinitionRegistry
from crxzipple.shared.runtime_console import TraceContext
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc


_TRACE_FIELD_NAMES = {
    "trace_id",
    "correlation_id",
    "session_key",
    "session_id",
    "active_session_id",
    "run_id",
    "turn_id",
    "step_id",
    "execution_item_id",
    "invocation_id",
    "tool_run_id",
    "tool_call_id",
    "llm_invocation_id",
    "llm_response_item_id",
    "session_item_id",
    "session_item_ids",
    "continuation_decision_id",
    "artifact_id",
    "approval_request_id",
    "message_id",
    "event_id",
    "source_event_id",
    "source_id",
}

_LINKED_ENTITY_FIELDS = {
    "session_key",
    "session_id",
    "active_session_id",
    "run_id",
    "turn_id",
    "step_id",
    "execution_item_id",
    "invocation_id",
    "tool_run_id",
    "tool_call_id",
    "llm_invocation_id",
    "llm_response_item_id",
    "session_item_id",
    "session_item_ids",
    "continuation_decision_id",
    "artifact_id",
    "approval_request_id",
    "message_id",
    "tool_id",
}


@dataclass(frozen=True, slots=True)
class TraceLinkedEntity:
    type: str
    id: str


@dataclass(frozen=True, slots=True)
class TraceEventView:
    event_id: str
    name: str
    family: str
    owner: str
    status: str
    timestamp: str
    relative_ms: int
    summary: str
    key_event: bool
    linked_entities: tuple[TraceLinkedEntity, ...]
    trace: TraceContext
    topic: str
    cursor: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class TraceSummaryView:
    trace_id: str
    status: str
    started_at: str | None
    completed_at: str | None
    duration_ms: int | None
    event_count: int
    key_event_count: int
    owners: tuple[str, ...]
    linked_entities: tuple[TraceLinkedEntity, ...]


@dataclass(slots=True)
class EventTraceReadModelProvider:
    events_service: EventsApplicationService
    definition_registry: EventDefinitionRegistry

    def get_trace(
        self,
        trace_id: str,
        *,
        aliases: set[str] | None = None,
        focus_id: str | None = None,
        limit: int = 200,
    ) -> TraceSummaryView:
        events = self.list_trace_events(
            trace_id,
            aliases=aliases,
            focus_id=focus_id,
            limit=limit,
        )
        timestamps = [
            datetime.fromisoformat(event.timestamp)
            for event in events
            if event.timestamp
        ]
        started_at = min(timestamps) if timestamps else None
        completed_at = max(timestamps) if timestamps else None
        owners = tuple(sorted({event.owner for event in events if event.owner}))
        linked_entities = _unique_entities(
            entity
            for event in events
            for entity in event.linked_entities
        )
        return TraceSummaryView(
            trace_id=trace_id,
            status=_trace_status(events),
            started_at=format_datetime_utc(started_at) if started_at is not None else None,
            completed_at=(
                format_datetime_utc(completed_at)
                if completed_at is not None
                else None
            ),
            duration_ms=_span_ms(started_at, completed_at),
            event_count=len(events),
            key_event_count=sum(1 for event in events if event.key_event),
            owners=owners,
            linked_entities=linked_entities,
        )

    def list_trace_events(
        self,
        trace_id: str,
        *,
        aliases: set[str] | None = None,
        focus_id: str | None = None,
        limit: int = 200,
    ) -> tuple[TraceEventView, ...]:
        normalized_aliases = {
            item.strip()
            for item in {trace_id, *(aliases or set())}
            if isinstance(item, str) and item.strip()
        }
        normalized_focus_id = focus_id.strip() if isinstance(focus_id, str) else ""
        if not normalized_aliases:
            return ()
        records: list[EventTopicRecord] = []
        per_topic_limit = per_topic_trace_limit(
            limit=limit,
            focus_id=normalized_focus_id,
        )
        for topic in trace_source_topics(
            events_service=self.events_service,
            registry=self.definition_registry,
        ):
            for record in self.events_service.read_recent_event_topic(
                topic,
                limit=per_topic_limit,
            ):
                if _record_matches_alias(record, normalized_aliases):
                    if normalized_focus_id and not _record_matches_alias(
                        record,
                        {normalized_focus_id},
                    ):
                        continue
                    records.append(record)
        records.sort(
            key=lambda record: (
                record.envelope.created_at,
                record.envelope.topic or "",
                record.cursor,
            ),
        )
        if len(records) > limit:
            records = records[-limit:]
        first_timestamp = records[0].envelope.created_at if records else None
        return tuple(
            self._event_view(
                record,
                trace_id=trace_id,
                first_timestamp=first_timestamp,
            )
            for record in records
        )

    def _event_view(
        self,
        record: EventTopicRecord,
        *,
        trace_id: str,
        first_timestamp: datetime | None,
    ) -> TraceEventView:
        envelope = record.envelope
        payload = dict(envelope.payload)
        event_name = envelope.event_name or ""
        definition = self.definition_registry.get_by_event_name(event_name)
        owner = definition.owner if definition is not None else _family_from_name(event_name)
        family = _family_from_owner(owner, event_name)
        trace_payload = _trace_payload(envelope.trace, payload, trace_id=trace_id)
        timestamp = coerce_utc_datetime(envelope.created_at)
        return TraceEventView(
            event_id=envelope.id,
            name=event_name or envelope.name or "event",
            family=family,
            owner=owner or "unknown",
            status=_status_from_payload(payload, kind=envelope.kind),
            timestamp=format_datetime_utc(timestamp),
            relative_ms=_span_ms(first_timestamp, timestamp) or 0,
            summary=_summary_from_payload(payload, event_name=event_name),
            key_event=envelope.kind != "live",
            linked_entities=_linked_entities(payload, envelope.trace),
            trace=TraceContext(
                trace_id=trace_id,
                correlation_id=_optional_str(trace_payload.get("correlation_id")),
                source_event_id=envelope.id,
                source_owner=owner,
                source_surface_id=_surface_id(self.definition_registry, event_name),
                source_event_name=event_name or None,
                session_key=_optional_str(trace_payload.get("session_key")),
                session_id=_optional_str(trace_payload.get("session_id"))
                or _optional_str(trace_payload.get("active_session_id")),
                turn_id=_optional_str(trace_payload.get("turn_id")),
                run_id=_optional_str(trace_payload.get("run_id")),
                step_id=_optional_str(trace_payload.get("step_id")),
                execution_item_id=_optional_str(trace_payload.get("execution_item_id")),
                tool_run_id=_optional_str(trace_payload.get("tool_run_id")),
                tool_call_id=_optional_str(trace_payload.get("tool_call_id")),
                llm_invocation_id=(
                    _optional_str(trace_payload.get("llm_invocation_id"))
                    or _optional_str(trace_payload.get("invocation_id"))
                ),
                llm_response_item_id=_optional_str(
                    trace_payload.get("llm_response_item_id"),
                ),
                session_item_id=(
                    _optional_str(trace_payload.get("session_item_id"))
                    or _first_optional_str(trace_payload.get("session_item_ids"))
                ),
                continuation_decision_id=_optional_str(
                    trace_payload.get("continuation_decision_id"),
                ),
                artifact_id=_optional_str(trace_payload.get("artifact_id")),
                approval_request_id=_optional_str(trace_payload.get("approval_request_id")),
            ),
            topic=envelope.topic or "",
            cursor=record.cursor,
            payload=payload,
        )


def _record_matches_alias(record: EventTopicRecord, aliases: set[str]) -> bool:
    if record.envelope.id in aliases:
        return True
    payload = dict(record.envelope.payload)
    trace = dict(record.envelope.trace)
    values = _collect_nested_scalar_values(payload, field_names=_TRACE_FIELD_NAMES)
    values.update(_collect_nested_scalar_values(trace, field_names=_TRACE_FIELD_NAMES))
    return bool(values.intersection(aliases))


def _trace_payload(
    trace: dict[str, Any],
    payload: dict[str, Any],
    *,
    trace_id: str,
) -> dict[str, Any]:
    merged = {"trace_id": trace_id, **trace}
    for field_name in (*_TRACE_FIELD_NAMES, "session_key", "session_id", "active_session_id"):
        if field_name not in merged and field_name in payload:
            merged[field_name] = payload[field_name]
    return merged


def _linked_entities(
    payload: dict[str, Any],
    trace: dict[str, Any],
) -> tuple[TraceLinkedEntity, ...]:
    entities: list[TraceLinkedEntity] = []
    for source in (payload, trace):
        for field_name, values in _collect_nested_values_by_field(
            source,
            field_names=_LINKED_ENTITY_FIELDS,
        ).items():
            for value in values:
                entities.append(TraceLinkedEntity(type=field_name, id=value))
    return _unique_entities(entities)


def _unique_entities(items) -> tuple[TraceLinkedEntity, ...]:  # noqa: ANN001
    seen: set[tuple[str, str]] = set()
    unique: list[TraceLinkedEntity] = []
    for item in items:
        key = (item.type, item.id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return tuple(unique)


def _collect_nested_scalar_values(
    payload: dict[str, Any],
    *,
    field_names: set[str],
) -> set[str]:
    values_by_field = _collect_nested_values_by_field(payload, field_names=field_names)
    return {value for values in values_by_field.values() for value in values}


def _collect_nested_values_by_field(
    payload: dict[str, Any],
    *,
    field_names: set[str],
) -> dict[str, set[str]]:
    values: dict[str, set[str]] = {field_name: set() for field_name in field_names}
    stack: list[Any] = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, value in current.items():
                if key in field_names and value is not None:
                    normalized = str(value).strip()
                    if normalized:
                        values[key].add(normalized)
                if isinstance(value, (dict, list, tuple)):
                    stack.append(value)
        elif isinstance(current, (list, tuple)):
            stack.extend(current)
    return {key: item for key, item in values.items() if item}


def _status_from_payload(payload: dict[str, Any], *, kind: str) -> str:
    for key in ("status", "tool_status", "run_status", "result_status"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            normalized = value.strip()
            if normalized == "succeeded":
                return "success"
            return normalized
    event_name = payload.get("event_name")
    if isinstance(event_name, str):
        if event_name.endswith((".failed", ".cancelled", ".timed_out")):
            return "failed"
        if event_name.endswith((".succeeded", ".completed", ".delivered")):
            return "success"
        if event_name.endswith((".started", ".claimed", ".queued")):
            return "running"
    return "running" if kind == "live" else "success"


def _summary_from_payload(payload: dict[str, Any], *, event_name: str) -> str:
    repeated_probe_summary = _repeated_probe_summary(payload)
    if repeated_probe_summary is not None:
        return repeated_probe_summary
    for key in ("summary", "message", "reason", "error_message", "text_delta", "text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return _truncate(" ".join(value.split()), limit=120)
    if event_name:
        return event_name.replace(".", " ")
    return "Runtime event"


def _repeated_probe_summary(payload: dict[str, Any]) -> str | None:
    observation = payload.get("repeated_probe_observation")
    if not isinstance(observation, dict):
        metadata = payload.get("metadata")
        if isinstance(metadata, dict):
            observation = metadata.get("repeated_probe_observation")
    if not isinstance(observation, dict):
        return None
    repeated = observation.get("repeated")
    if not isinstance(repeated, list) or not repeated:
        return None
    first = repeated[0]
    if not isinstance(first, dict):
        return None
    count = _optional_int(first.get("count")) or 0
    target = (
        _optional_str(first.get("normalized_url"))
        or _optional_str(first.get("command_fingerprint"))
        or _optional_str(first.get("argument_fingerprint"))
        or _optional_str(first.get("key"))
        or "target"
    )
    repeated_count = _optional_int(observation.get("repeated_count")) or len(repeated)
    return _truncate(
        f"Repeated probes: {repeated_count} target(s), top={target} x{count}",
        limit=120,
    )


def _trace_status(events: tuple[TraceEventView, ...]) -> str:
    if any(event.status == "failed" for event in events):
        return "failed"
    if any(event.status in {"running", "queued", "waiting"} for event in events):
        return "running"
    if events:
        return "success"
    return "unknown"


def _family_from_owner(owner: str | None, event_name: str) -> str:
    owner_value = (owner or "").strip().lower()
    if owner_value:
        if owner_value == "orchestration":
            return "orchestration"
        if owner_value in {"tool", "llm", "events", "channel", "channels"}:
            return "channel" if owner_value == "channels" else owner_value
    return _family_from_name(event_name)


def _family_from_name(event_name: str) -> str:
    first = event_name.split(".", 1)[0].strip().lower()
    if first in {"channel", "orchestration", "llm", "tool", "events"}:
        return first
    if first in {"session", "dispatch"}:
        return "orchestration"
    return first or "events"


def _surface_id(
    registry: EventDefinitionRegistry,
    event_name: str,
) -> str | None:
    surfaces = registry.list_surfaces_for_event_name(event_name)
    return surfaces[0].surface_id if surfaces else None


def _span_ms(started_at: datetime | None, ended_at: datetime | None) -> int | None:
    if started_at is None or ended_at is None:
        return None
    start = coerce_utc_datetime(started_at)
    end = coerce_utc_datetime(ended_at)
    return max(int((end - start).total_seconds() * 1000), 0)


def _optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _first_optional_str(value: object) -> str | None:
    if not isinstance(value, list | tuple):
        return None
    for item in value:
        normalized = _optional_str(item)
        if normalized is not None:
            return normalized
    return None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _truncate(value: str, *, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: limit - 3].rstrip()}..."
