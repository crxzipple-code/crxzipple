from __future__ import annotations

from sqlalchemy import select

from crxzipple.core.db import SessionFactory
from crxzipple.modules.settings.domain.entities import SettingsOverride
from crxzipple.modules.settings.domain.exceptions import SettingsAlreadyExistsError
from crxzipple.modules.settings.infrastructure.persistence.domain_override_mappers import (
    apply_override_model,
    override_from_record,
    override_record_from_domain,
)
from crxzipple.modules.settings.infrastructure.persistence.models import (
    SettingsOverrideModel,
)
from crxzipple.modules.settings.infrastructure.persistence.repository_override_mappers import (
    _override_model,
    _override_record,
)
from crxzipple.modules.settings.infrastructure.persistence.repository_values import (
    _required_text,
)


class SqlAlchemySettingsOverrideRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def add(self, override: SettingsOverride) -> None:
        if self.get(override.id) is not None:
            raise SettingsAlreadyExistsError(
                f"settings override '{override.id}' already exists.",
            )
        with self._session_factory() as session:
            session.add(_override_model(override_record_from_domain(override)))
            session.commit()

    def save(self, override: SettingsOverride) -> None:
        with self._session_factory() as session:
            model = session.get(SettingsOverrideModel, override.id)
            stored = _override_model(override_record_from_domain(override))
            if model is None:
                session.add(stored)
            else:
                apply_override_model(model, stored)
            session.commit()

    def get(self, override_id: str) -> SettingsOverride | None:
        with self._session_factory() as session:
            model = session.get(
                SettingsOverrideModel,
                _required_text(override_id, "override id"),
            )
            if model is None:
                return None
            return override_from_record(_override_record(model))

    def list_for_resource(
        self,
        resource_id: str,
        *,
        environment: str | None = None,
        enabled_only: bool = False,
    ) -> tuple[SettingsOverride, ...]:
        with self._session_factory() as session:
            statement = (
                select(SettingsOverrideModel)
                .where(
                    SettingsOverrideModel.resource_id
                    == _required_text(resource_id, "resource id"),
                )
                .order_by(
                    SettingsOverrideModel.priority.asc(),
                    SettingsOverrideModel.override_id.asc(),
                )
            )
            if environment is not None:
                statement = statement.where(
                    SettingsOverrideModel.scope_key
                    == _required_text(environment, "environment"),
                )
            if enabled_only:
                statement = statement.where(SettingsOverrideModel.status == "active")
            return tuple(
                override_from_record(_override_record(model))
                for model in session.scalars(statement)
            )

    def list_for_resources(
        self,
        resource_ids: tuple[str, ...],
        *,
        environment: str | None = None,
        enabled_only: bool = False,
    ) -> dict[str, tuple[SettingsOverride, ...]]:
        normalized_ids = tuple(
            _required_text(resource_id, "resource id")
            for resource_id in resource_ids
            if str(resource_id or "").strip()
        )
        if not normalized_ids:
            return {}
        with self._session_factory() as session:
            statement = (
                select(SettingsOverrideModel)
                .where(SettingsOverrideModel.resource_id.in_(normalized_ids))
                .order_by(
                    SettingsOverrideModel.resource_id.asc(),
                    SettingsOverrideModel.priority.asc(),
                    SettingsOverrideModel.override_id.asc(),
                )
            )
            if environment is not None:
                statement = statement.where(
                    SettingsOverrideModel.scope_key
                    == _required_text(environment, "environment"),
                )
            if enabled_only:
                statement = statement.where(SettingsOverrideModel.status == "active")
            grouped: dict[str, list[SettingsOverride]] = {
                resource_id: [] for resource_id in normalized_ids
            }
            for model in session.scalars(statement):
                grouped.setdefault(model.resource_id, []).append(
                    override_from_record(_override_record(model)),
                )
            return {
                resource_id: tuple(items)
                for resource_id, items in grouped.items()
            }
