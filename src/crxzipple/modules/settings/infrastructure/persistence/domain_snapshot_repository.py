from __future__ import annotations

from sqlalchemy import select

from crxzipple.core.db import SessionFactory
from crxzipple.modules.settings.domain.entities import SettingsEffectiveSnapshot
from crxzipple.modules.settings.infrastructure.persistence.domain_repository_mappers import (
    _snapshot_from_record,
    _snapshot_record_from_domain,
)
from crxzipple.modules.settings.infrastructure.persistence.models import (
    SettingsEffectiveSnapshotModel,
)
from crxzipple.modules.settings.infrastructure.persistence.repository_mappers import (
    _optional_text,
    _required_text,
    _snapshot_model,
    _snapshot_record,
)


class SqlAlchemySettingsEffectiveSnapshotRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def add(self, snapshot: SettingsEffectiveSnapshot) -> None:
        record = _snapshot_record_from_domain(snapshot)
        with self._session_factory() as session:
            if record.is_current:
                previous = session.scalars(
                    select(SettingsEffectiveSnapshotModel).where(
                        SettingsEffectiveSnapshotModel.resource_id
                        == record.resource_id,
                        SettingsEffectiveSnapshotModel.scope_key == record.scope_key,
                        SettingsEffectiveSnapshotModel.is_current.is_(True),
                    ),
                ).all()
                for item in previous:
                    item.is_current = False
            session.add(_snapshot_model(record))
            session.commit()

    def get(self, snapshot_id: str) -> SettingsEffectiveSnapshot | None:
        with self._session_factory() as session:
            model = session.get(
                SettingsEffectiveSnapshotModel,
                _required_text(snapshot_id, "snapshot id"),
            )
            if model is None:
                return None
            return _snapshot_from_record(_snapshot_record(model))

    def latest_for_resource(
        self,
        resource_id: str,
        *,
        environment: str | None = None,
    ) -> SettingsEffectiveSnapshot | None:
        scope_key = _optional_text(environment) or "default"
        with self._session_factory() as session:
            model = session.scalars(
                select(SettingsEffectiveSnapshotModel)
                .where(
                    SettingsEffectiveSnapshotModel.resource_id
                    == _required_text(resource_id, "resource id"),
                    SettingsEffectiveSnapshotModel.scope_key == scope_key,
                    SettingsEffectiveSnapshotModel.is_current.is_(True),
                )
                .order_by(
                    SettingsEffectiveSnapshotModel.generated_at.desc(),
                    SettingsEffectiveSnapshotModel.snapshot_id.desc(),
                )
                .limit(1),
            ).first()
            if model is None:
                return None
            return _snapshot_from_record(_snapshot_record(model))
