from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.modules.operations.infrastructure.persistence.models import (
    OperationsEventTimeBucketModel,
    OperationsModuleObservationModel,
    OperationsObservedEventModel,
)
from crxzipple.modules.operations.infrastructure.persistence.observation_repository_mappers import (
    int_count_map,
    to_observed_event,
)
from crxzipple.modules.operations.infrastructure.persistence.projection_repository import (
    normalize_key,
)
from crxzipple.shared.time import coerce_utc_datetime


def record_module_summary(session: Any, event: OperationsObservedEvent) -> None:
    module = normalize_key(event.module)
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


def record_event_bucket(
    session: Any,
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


def recent_module_events(
    session: Any,
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
    return tuple(to_observed_event(row) for row in rows)


def _event_bucket_start(value: datetime) -> datetime:
    observed_at = coerce_utc_datetime(value)
    return observed_at.replace(minute=0, second=0, microsecond=0)


def _increment_count(value: Any, key: str) -> dict[str, int]:
    counts = int_count_map(value)
    counts[key] = counts.get(key, 0) + 1
    return counts
