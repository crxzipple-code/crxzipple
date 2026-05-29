from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select

from crxzipple.core.db import SessionFactory
from crxzipple.modules.operations.application.action_audit import (
    OperationsActionAudit,
)
from crxzipple.modules.operations.application.observation import (
    OperationsModuleObservation,
    OperationsObserverHeartbeat,
    OperationsObservedEvent,
    OperationsObservationSnapshot,
    OperationsProjection,
)
from crxzipple.modules.operations.infrastructure.persistence.models import (
    OperationsActionAuditModel,
    OperationsEventTimeBucketModel,
    OperationsModuleObservationModel,
    OperationsObservedEventModel,
    OperationsObserverHeartbeatModel,
    OperationsProjectionModel,
)
from crxzipple.shared.time import coerce_utc_datetime

_OBSERVATION_VERSION = 4
_RECENT_EVENTS_PER_MODULE = 80


class SqlAlchemyOperationsProjectionStore:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def record_projection(
        self,
        *,
        module: str,
        kind: str,
        payload: dict[str, Any],
        query_key: str = "default",
        updated_at: datetime | None = None,
    ) -> None:
        normalized_module = _normalize_key(module)
        normalized_kind = _normalize_key(kind)
        normalized_query_key = query_key.strip() or "default"
        projection_updated_at = coerce_utc_datetime(
            updated_at or datetime.now(timezone.utc),
        )
        with self._session_factory() as session:
            model = session.get(
                OperationsProjectionModel,
                (normalized_module, normalized_kind, normalized_query_key),
            )
            if model is None:
                model = OperationsProjectionModel(
                    module=normalized_module,
                    kind=normalized_kind,
                    query_key=normalized_query_key,
                    version=1,
                    updated_at=projection_updated_at,
                    payload=dict(payload),
                )
                session.add(model)
            else:
                model.version += 1
                model.updated_at = projection_updated_at
                model.payload = dict(payload)
            session.commit()

    def get_projection(
        self,
        *,
        module: str,
        kind: str,
        query_key: str = "default",
    ) -> OperationsProjection | None:
        with self._session_factory() as session:
            model = session.get(
                OperationsProjectionModel,
                (_normalize_key(module), _normalize_key(kind), query_key.strip() or "default"),
            )
            if model is None:
                return None
            return _to_projection(model)

    def list_projections(
        self,
        *,
        module: str | None = None,
    ) -> tuple[OperationsProjection, ...]:
        with self._session_factory() as session:
            statement = select(OperationsProjectionModel).order_by(
                OperationsProjectionModel.module.asc(),
                OperationsProjectionModel.kind.asc(),
                OperationsProjectionModel.query_key.asc(),
            )
            if module is not None:
                statement = statement.where(
                    OperationsProjectionModel.module == _normalize_key(module),
                )
            models = session.scalars(statement).all()
            return tuple(_to_projection(model) for model in models)

    def clear(
        self,
        *,
        module: str | None = None,
        kind: str | None = None,
    ) -> int:
        with self._session_factory() as session:
            statement = delete(OperationsProjectionModel)
            if module is not None:
                statement = statement.where(
                    OperationsProjectionModel.module == _normalize_key(module),
                )
            if kind is not None:
                statement = statement.where(
                    OperationsProjectionModel.kind == _normalize_key(kind),
                )
            result = session.execute(statement)
            session.commit()
            return int(result.rowcount or 0)


def _to_projection(model: OperationsProjectionModel) -> OperationsProjection:
    return OperationsProjection(
        module=model.module,
        kind=model.kind,
        query_key=model.query_key,
        updated_at=coerce_utc_datetime(model.updated_at),
        payload=dict(model.payload),
    )


def _normalize_key(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        raise ValueError("operations projection key cannot be blank")
    return normalized


class SqlAlchemyOperationsObservationStore:
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        recent_events_per_module: int = _RECENT_EVENTS_PER_MODULE,
    ) -> None:
        self._session_factory = session_factory
        self._recent_events_per_module = max(int(recent_events_per_module), 1)

    def record_observed_event(self, event: OperationsObservedEvent) -> None:
        self.record_observed_events((event,))

    def record_observed_events(
        self,
        events: tuple[OperationsObservedEvent, ...],
    ) -> None:
        observed_events = tuple(events)
        if not observed_events:
            return
        recorded_at = datetime.now(timezone.utc)
        with self._session_factory() as session:
            for event in observed_events:
                topic = _normalize_observation_key(event.topic, "topic")
                cursor = _normalize_observation_key(event.cursor, "cursor")
                existing = session.get(
                    OperationsObservedEventModel,
                    (topic, cursor),
                )
                if existing is not None:
                    _apply_observed_event_model(
                        existing,
                        event,
                        recorded_at=coerce_utc_datetime(existing.recorded_at),
                    )
                    continue
                session.add(
                    _observed_event_model(
                        event,
                        topic=topic,
                        cursor=cursor,
                        recorded_at=recorded_at,
                    ),
                )
                _record_module_summary(session, event)
                _record_event_bucket(session, event, updated_at=recorded_at)
                session.flush()
            session.commit()

    def record_observer_heartbeat(
        self,
        heartbeat: OperationsObserverHeartbeat,
    ) -> None:
        runtime_name = _normalize_observation_key(
            heartbeat.runtime_name,
            "runtime name",
        )
        worker_id = _normalize_observation_key(heartbeat.worker_id, "worker id")
        with self._session_factory() as session:
            model = session.get(
                OperationsObserverHeartbeatModel,
                (runtime_name, worker_id),
            )
            if model is None:
                model = OperationsObserverHeartbeatModel(
                    runtime_name=runtime_name,
                    worker_id=worker_id,
                    status=heartbeat.status,
                    started_at=(
                        coerce_utc_datetime(heartbeat.started_at)
                        if heartbeat.started_at is not None
                        else None
                    ),
                    last_seen_at=coerce_utc_datetime(heartbeat.last_seen_at),
                    processed_events=max(int(heartbeat.processed_events), 0),
                    idle_cycles=max(int(heartbeat.idle_cycles), 0),
                    subscription_count=max(int(heartbeat.subscription_count), 0),
                    poll_interval_seconds=heartbeat.poll_interval_seconds,
                    limit_per_subscription=heartbeat.limit_per_subscription,
                )
                session.add(model)
            else:
                model.status = heartbeat.status
                model.started_at = (
                    coerce_utc_datetime(heartbeat.started_at)
                    if heartbeat.started_at is not None
                    else None
                )
                model.last_seen_at = coerce_utc_datetime(heartbeat.last_seen_at)
                model.processed_events = max(int(heartbeat.processed_events), 0)
                model.idle_cycles = max(int(heartbeat.idle_cycles), 0)
                model.subscription_count = max(int(heartbeat.subscription_count), 0)
                model.poll_interval_seconds = heartbeat.poll_interval_seconds
                model.limit_per_subscription = heartbeat.limit_per_subscription
            session.commit()

    def reset(self) -> None:
        with self._session_factory() as session:
            session.execute(delete(OperationsEventTimeBucketModel))
            session.execute(delete(OperationsObservedEventModel))
            session.execute(delete(OperationsModuleObservationModel))
            session.execute(delete(OperationsObserverHeartbeatModel))
            session.commit()

    def get_module_observation(
        self,
        module: str,
    ) -> OperationsModuleObservation | None:
        normalized = module.strip().lower() if isinstance(module, str) else ""
        if not normalized:
            return None
        with self._session_factory() as session:
            model = session.get(OperationsModuleObservationModel, normalized)
            if model is None:
                return None
            return _to_module_observation(
                model,
                recent_events=_recent_module_events(
                    session,
                    module=normalized,
                    limit=self._recent_events_per_module,
                ),
            )

    def snapshot(self) -> OperationsObservationSnapshot:
        with self._session_factory() as session:
            module_models = session.scalars(
                select(OperationsModuleObservationModel).order_by(
                    OperationsModuleObservationModel.module.asc(),
                ),
            ).all()
            modules = tuple(
                _to_module_observation(
                    model,
                    recent_events=_recent_module_events(
                        session,
                        module=model.module,
                        limit=self._recent_events_per_module,
                    ),
                )
                for model in module_models
            )
            heartbeats = tuple(
                _to_observer_heartbeat(model)
                for model in session.scalars(
                    select(OperationsObserverHeartbeatModel).order_by(
                        OperationsObserverHeartbeatModel.runtime_name.asc(),
                        OperationsObserverHeartbeatModel.worker_id.asc(),
                    ),
                )
            )
        return OperationsObservationSnapshot(
            version=_OBSERVATION_VERSION,
            updated_at=_snapshot_updated_at(modules, heartbeats),
            modules=modules,
            observer_heartbeats=heartbeats,
        )

    def list_event_buckets(
        self,
        *,
        module: str | None = None,
        event_name: str | None = None,
        since: datetime | None = None,
        limit: int = 500,
    ) -> tuple[dict[str, Any], ...]:
        safe_limit = min(max(int(limit), 1), 2000)
        with self._session_factory() as session:
            statement = select(OperationsEventTimeBucketModel).order_by(
                OperationsEventTimeBucketModel.bucket_start.desc(),
                OperationsEventTimeBucketModel.module.asc(),
                OperationsEventTimeBucketModel.event_name.asc(),
                OperationsEventTimeBucketModel.status.asc(),
            )
            if module is not None:
                statement = statement.where(
                    OperationsEventTimeBucketModel.module == _normalize_key(module),
                )
            if event_name is not None:
                statement = statement.where(
                    OperationsEventTimeBucketModel.event_name
                    == _normalize_observation_key(event_name, "event name"),
                )
            if since is not None:
                statement = statement.where(
                    OperationsEventTimeBucketModel.bucket_start
                    >= coerce_utc_datetime(since),
                )
            rows = session.scalars(statement.limit(safe_limit)).all()
            return tuple(_event_bucket_payload(row) for row in rows)


def _observed_event_model(
    event: OperationsObservedEvent,
    *,
    topic: str,
    cursor: str,
    recorded_at: datetime,
) -> OperationsObservedEventModel:
    model = OperationsObservedEventModel(
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
        payload=dict(event.payload),
        recorded_at=coerce_utc_datetime(recorded_at),
    )
    return model


def _apply_observed_event_model(
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
    model.payload = dict(event.payload)
    model.recorded_at = coerce_utc_datetime(recorded_at)


def _record_module_summary(session, event: OperationsObservedEvent) -> None:  # noqa: ANN001
    module = _normalize_key(event.module)
    model = session.get(OperationsModuleObservationModel, module)
    if model is None:
        model = OperationsModuleObservationModel(
            module=module,
            owner=event.owner,
            updated_at=coerce_utc_datetime(event.occurred_at),
            event_count=0,
            status_counts={},
            event_name_counts={},
            last_event_id=None,
            last_event_name=None,
            last_topic=None,
            last_cursor=None,
            last_event_at=None,
        )
        session.add(model)

    model.owner = event.owner
    model.event_count = int(model.event_count or 0) + 1
    model.status_counts = _increment_count(model.status_counts, event.status)
    model.event_name_counts = _increment_count(
        model.event_name_counts,
        event.event_name,
    )
    occurred_at = coerce_utc_datetime(event.occurred_at)
    last_event_at = (
        coerce_utc_datetime(model.last_event_at)
        if model.last_event_at is not None
        else None
    )
    if last_event_at is None or occurred_at >= last_event_at:
        model.updated_at = occurred_at
        model.last_event_id = event.id
        model.last_event_name = event.event_name
        model.last_topic = event.topic
        model.last_cursor = event.cursor
        model.last_event_at = occurred_at


def _record_event_bucket(
    session,  # noqa: ANN001
    event: OperationsObservedEvent,
    *,
    updated_at: datetime,
) -> None:
    bucket_start = _event_bucket_start(event.occurred_at)
    model = session.get(
        OperationsEventTimeBucketModel,
        (event.module, event.event_name, event.status, bucket_start),
    )
    if model is None:
        model = OperationsEventTimeBucketModel(
            module=event.module,
            owner=event.owner,
            event_name=event.event_name,
            status=event.status,
            level=event.level,
            bucket_start=bucket_start,
            count=1,
            updated_at=coerce_utc_datetime(updated_at),
        )
        session.add(model)
        return
    model.owner = event.owner
    model.level = event.level
    model.count = int(model.count or 0) + 1
    model.updated_at = coerce_utc_datetime(updated_at)


def _event_bucket_start(value: datetime) -> datetime:
    observed_at = coerce_utc_datetime(value)
    return observed_at.replace(minute=0, second=0, microsecond=0)


def _recent_module_events(
    session,  # noqa: ANN001
    *,
    module: str,
    limit: int,
) -> tuple[OperationsObservedEvent, ...]:
    rows = session.scalars(
        select(OperationsObservedEventModel)
        .where(OperationsObservedEventModel.module == module)
        .order_by(
            OperationsObservedEventModel.occurred_at.desc(),
            OperationsObservedEventModel.topic.desc(),
            OperationsObservedEventModel.cursor.desc(),
        )
        .limit(max(int(limit), 1)),
    ).all()
    return tuple(_to_observed_event(row) for row in rows)


def _to_observed_event(model: OperationsObservedEventModel) -> OperationsObservedEvent:
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


def _to_module_observation(
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
        status_counts=_int_count_map(model.status_counts),
        event_name_counts=_int_count_map(model.event_name_counts),
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


def _to_observer_heartbeat(
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


def _event_bucket_payload(
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


def _snapshot_updated_at(
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


def _increment_count(value: Any, key: str) -> dict[str, int]:
    counts = _int_count_map(value)
    counts[key] = counts.get(key, 0) + 1
    return counts


def _int_count_map(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, item in value.items():
        key_text = str(key).strip()
        if key_text:
            result[key_text] = _int(item)
    return result


def _normalize_observation_key(value: str, label: str) -> str:
    normalized = value.strip() if isinstance(value, str) else ""
    if not normalized:
        raise ValueError(f"operations observation {label} cannot be blank")
    return normalized


class SqlAlchemyOperationsActionAuditStore:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def record_attempt(
        self,
        *,
        action_type: str,
        target_type: str,
        target_id: str | None,
        target: dict[str, Any],
        reason: str,
        dangerous: bool,
        risk: str,
        confirmation: bool,
        risk_acknowledged: bool,
        operator: str | None,
        source: str,
        metadata: dict[str, Any],
        created_at: datetime | None = None,
    ) -> OperationsActionAudit:
        now = coerce_utc_datetime(created_at or datetime.now(timezone.utc))
        model = OperationsActionAuditModel(
            audit_id=f"opact_{uuid4().hex}",
            action_type=_normalize_text(action_type, "action type"),
            target_type=_normalize_text(target_type, "target type"),
            target_id=_optional_text(target_id),
            target=dict(target),
            reason=_normalize_text(reason, "reason"),
            dangerous=bool(dangerous),
            risk=_normalize_text(risk, "risk"),
            confirmation=bool(confirmation),
            risk_acknowledged=bool(risk_acknowledged),
            operator=_optional_text(operator),
            source=_normalize_text(source, "source"),
            metadata_=dict(metadata),
            created_at=now,
            updated_at=now,
            status="attempted",
            result=None,
            error=None,
        )
        with self._session_factory() as session:
            session.add(model)
            session.commit()
            return _to_action_audit(model)

    def mark_succeeded(
        self,
        audit_id: str,
        *,
        result: dict[str, Any] | None = None,
        updated_at: datetime | None = None,
    ) -> OperationsActionAudit:
        return self._mark_terminal(
            audit_id,
            status="succeeded",
            result=dict(result) if result is not None else None,
            error=None,
            updated_at=updated_at,
        )

    def mark_failed(
        self,
        audit_id: str,
        *,
        error: dict[str, Any],
        updated_at: datetime | None = None,
    ) -> OperationsActionAudit:
        return self._mark_terminal(
            audit_id,
            status="failed",
            result=None,
            error=dict(error),
            updated_at=updated_at,
        )

    def list_recent(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[OperationsActionAudit, ...]:
        safe_limit = min(max(int(limit), 1), 200)
        safe_offset = max(int(offset), 0)
        with self._session_factory() as session:
            statement = (
                select(OperationsActionAuditModel)
                .order_by(
                    OperationsActionAuditModel.created_at.desc(),
                    OperationsActionAuditModel.audit_id.desc(),
                )
                .limit(safe_limit)
                .offset(safe_offset)
            )
            return tuple(_to_action_audit(model) for model in session.scalars(statement))

    def _mark_terminal(
        self,
        audit_id: str,
        *,
        status: str,
        result: dict[str, Any] | None,
        error: dict[str, Any] | None,
        updated_at: datetime | None,
    ) -> OperationsActionAudit:
        with self._session_factory() as session:
            model = session.get(OperationsActionAuditModel, audit_id)
            if model is None:
                raise LookupError(f"Operations action audit '{audit_id}' does not exist.")
            model.status = status
            model.result = result
            model.error = error
            model.updated_at = coerce_utc_datetime(
                updated_at or datetime.now(timezone.utc),
            )
            session.commit()
            return _to_action_audit(model)


def _to_action_audit(model: OperationsActionAuditModel) -> OperationsActionAudit:
    return OperationsActionAudit(
        audit_id=model.audit_id,
        action_type=model.action_type,
        target_type=model.target_type,
        target_id=model.target_id,
        target=dict(model.target),
        reason=model.reason,
        dangerous=bool(model.dangerous),
        risk=model.risk,
        confirmation=bool(model.confirmation),
        risk_acknowledged=bool(model.risk_acknowledged),
        operator=model.operator,
        source=model.source,
        metadata=dict(model.metadata_),
        created_at=coerce_utc_datetime(model.created_at),
        updated_at=coerce_utc_datetime(model.updated_at),
        status=model.status,
        result=dict(model.result) if model.result is not None else None,
        error=dict(model.error) if model.error is not None else None,
    )


def _normalize_text(value: str | None, label: str) -> str:
    normalized = _optional_text(value)
    if normalized is None:
        raise ValueError(f"operations action audit {label} cannot be blank")
    return normalized


def _optional_text(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


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
