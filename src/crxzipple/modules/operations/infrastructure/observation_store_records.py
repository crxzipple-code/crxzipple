from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.operations.application.observation_models import (
    OperationsModuleObservation,
    OperationsObserverHeartbeat,
    OperationsObservedEvent,
    OperationsObservationSnapshot,
)
from crxzipple.shared.time import coerce_utc_datetime

OBSERVATION_VERSION = 4


def empty_observation_snapshot() -> OperationsObservationSnapshot:
    return OperationsObservationSnapshot(
        version=OBSERVATION_VERSION,
        updated_at=None,
        modules=(),
        observer_heartbeats=(),
    )


def observation_snapshot_from_payload(payload: object) -> OperationsObservationSnapshot:
    if not isinstance(payload, dict):
        return empty_observation_snapshot()
    modules = tuple(
        module
        for item in payload.get("modules", ())
        if isinstance(item, dict)
        for module in (OperationsModuleObservation.from_payload(item),)
        if module is not None
    )
    observer_heartbeats = tuple(
        heartbeat
        for item in payload.get("observer_heartbeats", ())
        if isinstance(item, dict)
        for heartbeat in (OperationsObserverHeartbeat.from_payload(item),)
        if heartbeat is not None
    )
    return OperationsObservationSnapshot(
        version=max(_int(payload.get("version")), OBSERVATION_VERSION),
        updated_at=_parse_datetime(payload.get("updated_at")),
        modules=modules,
        observer_heartbeats=observer_heartbeats,
    )


def record_observed_event(
    snapshot: OperationsObservationSnapshot,
    event: OperationsObservedEvent,
    *,
    recent_limit: int,
) -> OperationsObservationSnapshot:
    modules_by_key = {module.module: module for module in snapshot.modules}
    current = modules_by_key.get(event.module)
    modules_by_key[event.module] = _record_module_event(
        current,
        event,
        recent_limit=recent_limit,
    )
    return OperationsObservationSnapshot(
        version=OBSERVATION_VERSION,
        updated_at=event.occurred_at,
        modules=tuple(modules_by_key[key] for key in sorted(modules_by_key)),
        observer_heartbeats=snapshot.observer_heartbeats,
    )


def record_observer_heartbeat(
    snapshot: OperationsObservationSnapshot,
    heartbeat: OperationsObserverHeartbeat,
) -> OperationsObservationSnapshot:
    heartbeats_by_key = {
        (item.runtime_name, item.worker_id): item
        for item in snapshot.observer_heartbeats
    }
    heartbeats_by_key[(heartbeat.runtime_name, heartbeat.worker_id)] = heartbeat
    latest_update = snapshot.updated_at
    heartbeat_seen_at = coerce_utc_datetime(heartbeat.last_seen_at)
    if latest_update is None or heartbeat_seen_at > coerce_utc_datetime(latest_update):
        latest_update = heartbeat_seen_at
    return OperationsObservationSnapshot(
        version=OBSERVATION_VERSION,
        updated_at=latest_update,
        modules=snapshot.modules,
        observer_heartbeats=tuple(
            heartbeats_by_key[key] for key in sorted(heartbeats_by_key)
        ),
    )


def _record_module_event(
    current: OperationsModuleObservation | None,
    event: OperationsObservedEvent,
    *,
    recent_limit: int,
) -> OperationsModuleObservation:
    status_counts = dict(current.status_counts) if current is not None else {}
    event_name_counts = dict(current.event_name_counts) if current is not None else {}
    status_counts[event.status] = status_counts.get(event.status, 0) + 1
    event_name_counts[event.event_name] = event_name_counts.get(event.event_name, 0) + 1
    recent_events = (event,)
    if current is not None:
        recent_events = recent_events + tuple(
            item
            for item in current.recent_events
            if item.id != event.id or item.cursor != event.cursor
        )
    return OperationsModuleObservation(
        module=event.module,
        owner=event.owner,
        updated_at=event.occurred_at,
        event_count=(current.event_count if current is not None else 0) + 1,
        status_counts=status_counts,
        event_name_counts=event_name_counts,
        last_event_id=event.id,
        last_event_name=event.event_name,
        last_topic=event.topic,
        last_cursor=event.cursor,
        last_event_at=event.occurred_at,
        recent_events=recent_events[:recent_limit],
    )


def _int(value: Any) -> int:
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


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return coerce_utc_datetime(datetime.fromisoformat(value))
    except ValueError:
        return None
