from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from crxzipple.modules.events.domain.entities import EventOutboxRecord
from crxzipple.modules.events.domain.value_objects import EventOutboxStatus
from crxzipple.modules.events.infrastructure.persistence.models import (
    EventOutboxRecordModel,
)
from crxzipple.shared.time import (
    coerce_optional_utc_datetime,
    coerce_utc_datetime,
)


class SqlAlchemyEventOutboxRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._pending_models: dict[str, EventOutboxRecordModel] = {}

    def add(self, record: EventOutboxRecord) -> None:
        model = self._pending_models.get(record.id)
        if model is None:
            with self.session.no_autoflush:
                model = self.session.get(EventOutboxRecordModel, record.id)
            if model is None:
                model = EventOutboxRecordModel(
                    id=record.id,
                    topic=record.topic,
                    status=record.status.value,
                    attempts=record.attempts,
                    event_payload=record.event_payload,
                    created_at=record.created_at,
                    updated_at=record.updated_at,
                    available_at=record.available_at,
                    publisher_id=record.publisher_id,
                    claim_expires_at=record.claim_expires_at,
                )
                self.session.add(model)
            self._pending_models[record.id] = model
        model.topic = record.topic
        model.event_name = record.event_name
        model.status = record.status.value
        model.attempts = record.attempts
        model.event_payload = dict(record.event_payload)
        model.error_message = record.error_message
        model.created_at = record.created_at
        model.updated_at = record.updated_at
        model.available_at = record.available_at
        model.publisher_id = record.publisher_id
        model.claim_expires_at = record.claim_expires_at
        model.delivered_at = record.delivered_at

    def get(self, record_id: str) -> EventOutboxRecord | None:
        model = self._pending_models.get(record_id)
        if model is None:
            model = self.session.get(EventOutboxRecordModel, record_id)
        return self._to_entity(model) if model is not None else None

    def list_publishable(
        self,
        *,
        limit: int = 100,
        now: datetime | None = None,
    ) -> list[EventOutboxRecord]:
        cutoff = coerce_utc_datetime(now or datetime.now(timezone.utc))
        models = list(
            self.session.scalars(
                select(EventOutboxRecordModel)
                .where(
                    EventOutboxRecordModel.status.in_(
                        (
                            EventOutboxStatus.PENDING.value,
                            EventOutboxStatus.FAILED.value,
                        ),
                    ),
                    EventOutboxRecordModel.available_at <= cutoff,
                )
                .order_by(
                    EventOutboxRecordModel.created_at.asc(),
                    EventOutboxRecordModel.id.asc(),
                )
                .limit(limit),
            ).all(),
        )
        return [self._to_entity(model) for model in models]

    def claim_publishable(
        self,
        *,
        publisher_id: str,
        limit: int = 100,
        claim_seconds: int = 60,
        now: datetime | None = None,
    ) -> list[EventOutboxRecord]:
        normalized_publisher_id = publisher_id.strip()
        if not normalized_publisher_id:
            raise ValueError("Event outbox publisher_id cannot be empty.")
        cutoff = coerce_utc_datetime(now or datetime.now(timezone.utc))
        lease_until = cutoff + timedelta(seconds=max(int(claim_seconds), 1))
        candidate_ids = list(
            self.session.scalars(
                select(EventOutboxRecordModel.id)
                .where(_publishable_filter(cutoff))
                .order_by(
                    EventOutboxRecordModel.created_at.asc(),
                    EventOutboxRecordModel.id.asc(),
                )
                .limit(max(int(limit), 1)),
            ).all(),
        )
        claimed: list[EventOutboxRecord] = []
        for candidate_id in candidate_ids:
            updated = self.session.execute(
                update(EventOutboxRecordModel)
                .where(
                    EventOutboxRecordModel.id == candidate_id,
                    _publishable_filter(cutoff),
                )
                .values(
                    status=EventOutboxStatus.PUBLISHING.value,
                    publisher_id=normalized_publisher_id,
                    claim_expires_at=lease_until,
                    updated_at=cutoff,
                ),
            )
            if updated.rowcount != 1:
                continue
            self.session.flush()
            model = self.session.get(EventOutboxRecordModel, candidate_id)
            if model is not None:
                self._pending_models[candidate_id] = model
                claimed.append(self._to_entity(model))
        return claimed

    def list(
        self,
        *,
        status: EventOutboxStatus | None = None,
        limit: int = 100,
    ) -> list[EventOutboxRecord]:
        statement = select(EventOutboxRecordModel)
        if status is not None:
            statement = statement.where(EventOutboxRecordModel.status == status.value)
        models = list(
            self.session.scalars(
                statement.order_by(
                    EventOutboxRecordModel.created_at.desc(),
                    EventOutboxRecordModel.id.desc(),
                ).limit(limit),
            ).all(),
        )
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_entity(model: EventOutboxRecordModel) -> EventOutboxRecord:
        return EventOutboxRecord(
            id=model.id,
            topic=model.topic,
            event_name=model.event_name,
            status=EventOutboxStatus(model.status),
            attempts=model.attempts,
            event_payload=dict(model.event_payload),
            error_message=model.error_message,
            created_at=coerce_utc_datetime(model.created_at),
            updated_at=coerce_utc_datetime(model.updated_at),
            available_at=coerce_utc_datetime(model.available_at),
            publisher_id=model.publisher_id,
            claim_expires_at=coerce_optional_utc_datetime(model.claim_expires_at),
            delivered_at=coerce_optional_utc_datetime(model.delivered_at),
        )


def _publishable_filter(cutoff: datetime):
    return or_(
        and_(
            EventOutboxRecordModel.status.in_(
                (
                    EventOutboxStatus.PENDING.value,
                    EventOutboxStatus.FAILED.value,
                ),
            ),
            EventOutboxRecordModel.available_at <= cutoff,
        ),
        and_(
            EventOutboxRecordModel.status == EventOutboxStatus.PUBLISHING.value,
            EventOutboxRecordModel.claim_expires_at.is_not(None),
            EventOutboxRecordModel.claim_expires_at <= cutoff,
        ),
    )
