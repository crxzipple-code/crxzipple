from __future__ import annotations

from sqlalchemy import select

from crxzipple.core.db import SessionFactory
from crxzipple.modules.settings.domain.entities import SettingsResourceVersion
from crxzipple.modules.settings.domain.exceptions import SettingsAlreadyExistsError
from crxzipple.modules.settings.infrastructure.persistence.domain_repository_mappers import (
    _apply_version,
    _apply_version_to_resource,
    _version_from_record,
    _version_record_from_domain,
)
from crxzipple.modules.settings.infrastructure.persistence.models import (
    SettingsResourceModel,
    SettingsResourceVersionModel,
)
from crxzipple.modules.settings.infrastructure.persistence.repository_mappers import (
    _required_text,
    _version_model,
    _version_record,
)


class SqlAlchemySettingsResourceVersionRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def add(self, version: SettingsResourceVersion) -> None:
        if self.get(version.id) is not None:
            raise SettingsAlreadyExistsError(
                f"settings version '{version.id}' already exists.",
            )
        with self._session_factory() as session:
            model = _version_model(_version_record_from_domain(version))
            session.add(model)
            resource = session.get(SettingsResourceModel, version.resource_id)
            if resource is not None:
                _apply_version_to_resource(resource, model)
            session.commit()

    def save(self, version: SettingsResourceVersion) -> None:
        with self._session_factory() as session:
            model = session.get(SettingsResourceVersionModel, version.id)
            stored = _version_model(_version_record_from_domain(version))
            if model is None:
                session.add(stored)
                model = stored
            else:
                _apply_version(model, stored)
            resource = session.get(SettingsResourceModel, version.resource_id)
            if resource is not None:
                _apply_version_to_resource(resource, model)
            session.commit()

    def get(self, version_id: str) -> SettingsResourceVersion | None:
        with self._session_factory() as session:
            model = session.get(
                SettingsResourceVersionModel,
                _required_text(version_id, "version id"),
            )
            if model is None:
                return None
            return _version_from_record(_version_record(model))

    def list_for_resource(self, resource_id: str) -> tuple[SettingsResourceVersion, ...]:
        with self._session_factory() as session:
            models = session.scalars(
                select(SettingsResourceVersionModel)
                .where(
                    SettingsResourceVersionModel.resource_id
                    == _required_text(resource_id, "resource id"),
                )
                .order_by(SettingsResourceVersionModel.version_number.asc()),
            ).all()
            return tuple(_version_from_record(_version_record(model)) for model in models)

    def latest_for_resource(self, resource_id: str) -> SettingsResourceVersion | None:
        versions = self.list_for_resource(resource_id)
        return versions[-1] if versions else None

    def latest_published_for_resource(
        self,
        resource_id: str,
    ) -> SettingsResourceVersion | None:
        with self._session_factory() as session:
            model = session.scalars(
                select(SettingsResourceVersionModel)
                .where(
                    SettingsResourceVersionModel.resource_id
                    == _required_text(resource_id, "resource id"),
                    SettingsResourceVersionModel.status == "published",
                )
                .order_by(
                    SettingsResourceVersionModel.version_number.desc(),
                    SettingsResourceVersionModel.created_at.desc(),
                )
                .limit(1),
            ).first()
            if model is None:
                return None
            return _version_from_record(_version_record(model))

    def latest_published_for_resources(
        self,
        resource_ids: tuple[str, ...],
    ) -> dict[str, SettingsResourceVersion]:
        normalized_ids = tuple(
            _required_text(resource_id, "resource id")
            for resource_id in resource_ids
            if str(resource_id or "").strip()
        )
        if not normalized_ids:
            return {}
        with self._session_factory() as session:
            models = session.scalars(
                select(SettingsResourceVersionModel)
                .where(
                    SettingsResourceVersionModel.resource_id.in_(normalized_ids),
                    SettingsResourceVersionModel.status == "published",
                )
                .order_by(
                    SettingsResourceVersionModel.resource_id.asc(),
                    SettingsResourceVersionModel.version_number.desc(),
                    SettingsResourceVersionModel.created_at.desc(),
                ),
            ).all()
            latest: dict[str, SettingsResourceVersion] = {}
            for model in models:
                if model.resource_id in latest:
                    continue
                latest[model.resource_id] = _version_from_record(
                    _version_record(model),
                )
            return latest
