from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from crxzipple.modules.events import EventTopicRecord
from crxzipple.shared import EventDefinitionRegistry


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
            owner=normalize_optional_text(owner),
            surface_id=normalize_optional_text(surface_id),
            event_name=normalize_optional_text(event_name),
            topic_prefix=normalize_optional_text(topic_prefix),
            run_id=normalize_optional_text(run_id),
            session_key=normalize_optional_text(session_key),
            interaction_id=normalize_optional_text(interaction_id),
            channel_type=normalize_optional_text(channel_type),
            payload_key=normalize_optional_text(payload_key),
            payload_value=normalize_optional_text(payload_value),
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


def console_topic_record_summary(
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


def read_recent_console_records(
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
                and compare_event_cursors(record.cursor, up_to_cursor) > 0
            ):
                continue
            summary = console_topic_record_summary(
                record,
                definition_registry=definition_registry,
            )
            if matches_console_stream_filters(summary, filters):
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


def snapshot_console_topics(
    *,
    events_service,
    filters: EventConsoleStreamFilters,
) -> dict[str, str | None]:
    topics = list_console_topics(
        events_service=events_service,
        filters=filters,
    )
    return {
        topic: events_service.snapshot_event_topic(topic)
        for topic in topics
    }


def refresh_console_topics(
    *,
    events_service,
    existing_cursors: dict[str, str | None],
    filters: EventConsoleStreamFilters,
) -> dict[str, str | None]:
    refreshed = dict(existing_cursors)
    for topic in list_console_topics(
        events_service=events_service,
        filters=filters,
    ):
        refreshed.setdefault(topic, None)
    return refreshed


def list_console_topics(
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


def sort_console_records(
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


def matches_console_stream_filters(
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
        and filters.run_id not in collect_nested_scalar_values(
            source_payload,
            field_names={"run_id", "source_id"},
        )
    ):
        return False
    if (
        filters.session_key is not None
        and filters.session_key not in collect_nested_scalar_values(
            source_payload,
            field_names={"session_key"},
        )
    ):
        return False
    if (
        filters.interaction_id is not None
        and filters.interaction_id not in collect_nested_scalar_values(
            source_payload,
            field_names={"interaction_id"},
        )
    ):
        return False
    if (
        filters.channel_type is not None
        and filters.channel_type not in collect_nested_scalar_values(
            {
                "source_payload": source_payload,
                "source_target": dict(summary.get("source_target") or {}),
            },
            field_names={"channel_type", "transport"},
        )
    ):
        return False
    if filters.payload_key is not None:
        payload_value = payload_lookup(source_payload, filters.payload_key)
        if filters.payload_value is None:
            if payload_value is None:
                return False
        elif not payload_value_matches(payload_value, filters.payload_value):
            return False
    return True


def collect_nested_scalar_values(
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


def payload_lookup(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        key = part.strip()
        if not key:
            return None
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def payload_value_matches(value: Any, expected: str) -> bool:
    if isinstance(value, (list, tuple, set)):
        return expected in {str(item).strip() for item in value if item is not None}
    if isinstance(value, dict):
        return False
    return str(value).strip() == expected


def normalize_optional_text(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def format_sse_event(event_name: str, payload: dict[str, Any]) -> str:
    return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def compare_event_cursors(left: str | None, right: str | None) -> int:
    left_cursor = parse_event_cursor(left)
    right_cursor = parse_event_cursor(right)
    if left_cursor == right_cursor:
        return 0
    return 1 if left_cursor > right_cursor else -1


def parse_event_cursor(cursor: str | None) -> tuple[int, int]:
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
