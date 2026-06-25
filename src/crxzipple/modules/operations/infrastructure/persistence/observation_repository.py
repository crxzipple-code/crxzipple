from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select

from crxzipple.core.db import SessionFactory
from crxzipple.modules.operations.application.observation_models import (
    OperationsModuleObservation,
    OperationsObserverHeartbeat,
    OperationsObservedEvent,
    OperationsObservationSnapshot,
)
from crxzipple.modules.operations.infrastructure.persistence.models import (
    OperationsEventTimeBucketModel,
    OperationsModuleObservationModel,
    OperationsObservedEventModel,
    OperationsObserverHeartbeatModel,
)
from crxzipple.modules.operations.infrastructure.persistence.observation_repository_heartbeats import (
    upsert_observer_heartbeat,
)
from crxzipple.modules.operations.infrastructure.persistence.observation_repository_mappers import (
    apply_observed_event_model,
    event_bucket_payload,
    normalize_observation_key,
    observed_event_model,
    snapshot_updated_at,
    to_module_observation,
    to_observer_heartbeat,
)
from crxzipple.modules.operations.infrastructure.persistence.observation_repository_recording import (
    recent_module_events,
    record_event_bucket,
    record_module_summary,
)
from crxzipple.modules.operations.infrastructure.persistence.projection_repository import (
    normalize_key,
)
from crxzipple.shared.time import coerce_utc_datetime

_OBSERVATION_VERSION = 4
_RECENT_EVENTS_PER_MODULE = 80


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
                topic = normalize_observation_key(event.topic, "topic")
                cursor = normalize_observation_key(event.cursor, "cursor")
                existing = session.get(
                    OperationsObservedEventModel,
                    (topic, cursor),
                )
                if existing is not None:
                    apply_observed_event_model(
                        existing,
                        event,
                        recorded_at=coerce_utc_datetime(existing.recorded_at),
                    )
                    continue
                session.add(
                    observed_event_model(
                        event,
                        topic=topic,
                        cursor=cursor,
                        recorded_at=recorded_at,
                    ),
                )
                record_module_summary(session, event)
                record_event_bucket(session, event, updated_at=recorded_at)
                session.flush()
            session.commit()

    def record_observer_heartbeat(
        self,
        heartbeat: OperationsObserverHeartbeat,
    ) -> None:
        with self._session_factory() as session:
            upsert_observer_heartbeat(session, heartbeat)
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
            return to_module_observation(
                model,
                recent_events=recent_module_events(
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
                to_module_observation(
                    model,
                    recent_events=recent_module_events(
                        session,
                        module=model.module,
                        limit=self._recent_events_per_module,
                    ),
                )
                for model in module_models
            )
            heartbeats = tuple(
                to_observer_heartbeat(model)
                for model in session.scalars(
                    select(OperationsObserverHeartbeatModel).order_by(
                        OperationsObserverHeartbeatModel.runtime_name.asc(),
                        OperationsObserverHeartbeatModel.worker_id.asc(),
                    ),
                )
            )
        return OperationsObservationSnapshot(
            version=_OBSERVATION_VERSION,
            updated_at=snapshot_updated_at(modules, heartbeats),
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
                    OperationsEventTimeBucketModel.module == normalize_key(module),
                )
            if event_name is not None:
                statement = statement.where(
                    OperationsEventTimeBucketModel.event_name
                    == normalize_observation_key(event_name, "event name"),
                )
            if since is not None:
                statement = statement.where(
                    OperationsEventTimeBucketModel.bucket_start
                    >= coerce_utc_datetime(since),
                )
            rows = session.scalars(statement.limit(safe_limit)).all()
            return tuple(event_bucket_payload(row) for row in rows)
