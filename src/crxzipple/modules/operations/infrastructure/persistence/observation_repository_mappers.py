from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.operations.application.observation_models import (
    OperationsModuleObservation,
    OperationsObserverHeartbeat,
    OperationsObservedEvent,
)
from crxzipple.modules.operations.application.observation_payloads import (
    redact_sensitive_payload,
)
from crxzipple.modules.operations.infrastructure.persistence.models import (
    OperationsEventTimeBucketModel,
    OperationsModuleObservationModel,
    OperationsObservedEventModel,
    OperationsObserverHeartbeatModel,
)
from crxzipple.shared.time import coerce_utc_datetime


def observed_event_model(
    event: OperationsObservedEvent,
    *,
    topic: str,
    cursor: str,
    recorded_at: datetime,
) -> OperationsObservedEventModel:
    return OperationsObservedEventModel(
        topic=topic,
        cursor=cursor,
        event_id=event.id,
        event_name=event.event_name,
        module=event.module,
        owner=event.owner,
        kind=event.kind,
        level=event.level,
        status=event.status,
        entity_id=event.entity_id,
        run_id=event.run_id,
        trace_id=event.trace_id,
        source_event_name=event.source_event_name,
        occurred_at=coerce_utc_datetime(event.occurred_at),
        payload=dict(redact_sensitive_payload(event.payload)),
        recorded_at=coerce_utc_datetime(recorded_at),
    )


def apply_observed_event_model(
    model: OperationsObservedEventModel,
    event: OperationsObservedEvent,
    *,
    recorded_at: datetime,
) -> None:
    model.event_id = event.id
    model.event_name = event.event_name
    model.module = event.module
    model.owner = event.owner
    model.kind = event.kind
    model.level = event.level
    model.status = event.status
    model.entity_id = event.entity_id
    model.run_id = event.run_id
    model.trace_id = event.trace_id
    model.source_event_name = event.source_event_name
    model.occurred_at = coerce_utc_datetime(event.occurred_at)
    model.payload = dict(redact_sensitive_payload(event.payload))
    model.recorded_at = coerce_utc_datetime(recorded_at)


def to_observed_event(model: OperationsObservedEventModel) -> OperationsObservedEvent:
    return OperationsObservedEvent(
        id=model.event_id,
        cursor=model.cursor,
        topic=model.topic,
        event_name=model.event_name,
        module=model.module,
        owner=model.owner,
        kind=model.kind,
        level=model.level,
        status=model.status,
        entity_id=model.entity_id,
        run_id=model.run_id,
        trace_id=model.trace_id,
        source_event_name=model.source_event_name,
        occurred_at=coerce_utc_datetime(model.occurred_at),
        payload=dict(model.payload or {}),
    )


def to_module_observation(
    model: OperationsModuleObservationModel,
    *,
    recent_events: tuple[OperationsObservedEvent, ...],
) -> OperationsModuleObservation:
    return OperationsModuleObservation(
        module=model.module,
        owner=model.owner,
        updated_at=(
            coerce_utc_datetime(model.updated_at)
            if model.updated_at is not None
            else None
        ),
        event_count=int(model.event_count or 0),
        status_counts=int_count_map(model.status_counts),
        event_name_counts=int_count_map(model.event_name_counts),
        last_event_id=model.last_event_id,
        last_event_name=model.last_event_name,
        last_topic=model.last_topic,
        last_cursor=model.last_cursor,
        last_event_at=(
            coerce_utc_datetime(model.last_event_at)
            if model.last_event_at is not None
            else None
        ),
        recent_events=recent_events,
    )


def to_observer_heartbeat(
    model: OperationsObserverHeartbeatModel,
) -> OperationsObserverHeartbeat:
    return OperationsObserverHeartbeat(
        runtime_name=model.runtime_name,
        worker_id=model.worker_id,
        status=model.status,
        started_at=(
            coerce_utc_datetime(model.started_at)
            if model.started_at is not None
            else None
        ),
        last_seen_at=coerce_utc_datetime(model.last_seen_at),
        processed_events=int(model.processed_events or 0),
        idle_cycles=int(model.idle_cycles or 0),
        subscription_count=int(model.subscription_count or 0),
        poll_interval_seconds=model.poll_interval_seconds,
        limit_per_subscription=model.limit_per_subscription,
    )


def event_bucket_payload(
    model: OperationsEventTimeBucketModel,
) -> dict[str, Any]:
    return {
        "module": model.module,
        "owner": model.owner,
        "event_name": model.event_name,
        "status": model.status,
        "level": model.level,
        "bucket_start": coerce_utc_datetime(model.bucket_start),
        "count": int(model.count or 0),
        "updated_at": coerce_utc_datetime(model.updated_at),
    }


def snapshot_updated_at(
    modules: tuple[OperationsModuleObservation, ...],
    heartbeats: tuple[OperationsObserverHeartbeat, ...],
) -> datetime | None:
    timestamps: list[datetime] = []
    for module in modules:
        if module.updated_at is not None:
            timestamps.append(coerce_utc_datetime(module.updated_at))
    for heartbeat in heartbeats:
        timestamps.append(coerce_utc_datetime(heartbeat.last_seen_at))
    return max(timestamps) if timestamps else None


def int_count_map(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, item in value.items():
        key_text = str(key).strip()
        if key_text:
            result[key_text] = int_value(item)
    return result


def normalize_observation_key(value: str, label: str) -> str:
    normalized = value.strip() if isinstance(value, str) else ""
    if not normalized:
        raise ValueError(f"operations observation {label} cannot be blank")
    return normalized


def int_value(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(float(value))
        except ValueError:
            return 0
    return 0
