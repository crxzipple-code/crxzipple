from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.observation_models import (
    OperationsObserverHeartbeat,
)
from crxzipple.modules.operations.infrastructure.persistence.models import (
    OperationsObserverHeartbeatModel,
)
from crxzipple.modules.operations.infrastructure.persistence.observation_repository_mappers import (
    normalize_observation_key,
)
from crxzipple.shared.time import coerce_utc_datetime


def upsert_observer_heartbeat(
    session: Any,
    heartbeat: OperationsObserverHeartbeat,
) -> None:
    runtime_name = normalize_observation_key(
        heartbeat.runtime_name,
        "runtime name",
    )
    worker_id = normalize_observation_key(heartbeat.worker_id, "worker id")
    model = session.get(
        OperationsObserverHeartbeatModel,
        (runtime_name, worker_id),
    )
    if model is None:
        session.add(_observer_heartbeat_model(heartbeat, runtime_name, worker_id))
        return
    model.status = heartbeat.status
    model.started_at = _started_at(heartbeat)
    model.last_seen_at = coerce_utc_datetime(heartbeat.last_seen_at)
    model.processed_events = max(int(heartbeat.processed_events), 0)
    model.idle_cycles = max(int(heartbeat.idle_cycles), 0)
    model.subscription_count = max(int(heartbeat.subscription_count), 0)
    model.poll_interval_seconds = heartbeat.poll_interval_seconds
    model.limit_per_subscription = heartbeat.limit_per_subscription


def _observer_heartbeat_model(
    heartbeat: OperationsObserverHeartbeat,
    runtime_name: str,
    worker_id: str,
) -> OperationsObserverHeartbeatModel:
    return OperationsObserverHeartbeatModel(
        runtime_name=runtime_name,
        worker_id=worker_id,
        status=heartbeat.status,
        started_at=_started_at(heartbeat),
        last_seen_at=coerce_utc_datetime(heartbeat.last_seen_at),
        processed_events=max(int(heartbeat.processed_events), 0),
        idle_cycles=max(int(heartbeat.idle_cycles), 0),
        subscription_count=max(int(heartbeat.subscription_count), 0),
        poll_interval_seconds=heartbeat.poll_interval_seconds,
        limit_per_subscription=heartbeat.limit_per_subscription,
    )


def _started_at(heartbeat: OperationsObserverHeartbeat) -> object:
    if heartbeat.started_at is None:
        return None
    return coerce_utc_datetime(heartbeat.started_at)
