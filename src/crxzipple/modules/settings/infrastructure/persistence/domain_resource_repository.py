from __future__ import annotations

from sqlalchemy import select

from crxzipple.core.db import SessionFactory
from crxzipple.modules.settings.domain.entities import SettingsResource
from crxzipple.modules.settings.domain.exceptions import SettingsAlreadyExistsError
from crxzipple.modules.settings.infrastructure.persistence.domain_resource_mappers import (
    resource_from_record,
    resource_record_from_domain,
)
from crxzipple.modules.settings.infrastructure.persistence.models import (
    SettingsResourceModel,
)
from crxzipple.modules.settings.infrastructure.persistence.repository_resource_mappers import (
    _apply_resource,
    _resource_model,
    _resource_record,
)
from crxzipple.modules.settings.infrastructure.persistence.repository_values import (
    _required_text,
)


class SqlAlchemySettingsResourceRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def add(self, resource: SettingsResource) -> None:
        if self.get(resource.id) is not None:
            raise SettingsAlreadyExistsError(
                f"settings resource '{resource.id}' already exists.",
            )
        with self._session_factory() as session:
            session.add(_resource_model(resource_record_from_domain(resource)))
            session.commit()

    def save(self, resource: SettingsResource) -> None:
        with self._session_factory() as session:
            model = session.get(SettingsResourceModel, resource.id)
            if model is None:
                session.add(_resource_model(resource_record_from_domain(resource)))
            else:
                _apply_resource(model, resource_record_from_domain(resource))
            session.commit()

    def get(self, resource_id: str) -> SettingsResource | None:
        with self._session_factory() as session:
            model = session.get(
                SettingsResourceModel,
                _required_text(resource_id, "resource id"),
            )
            if model is None:
                return None
            return resource_from_record(_resource_record(model))

    def list(
        self,
        *,
        resource_kind: str | None = None,
        owner_module: str | None = None,
    ) -> tuple[SettingsResource, ...]:
        with self._session_factory() as session:
            statement = select(SettingsResourceModel).order_by(
                SettingsResourceModel.resource_kind.asc(),
                SettingsResourceModel.resource_id.asc(),
            )
            if resource_kind is not None:
                statement = statement.where(
                    SettingsResourceModel.resource_kind
                    == _required_text(resource_kind, "resource kind"),
                )
            resources = tuple(
                resource_from_record(_resource_record(model))
                for model in session.scalars(statement)
            )
        if owner_module is not None:
            normalized_owner = owner_module.strip()
            resources = tuple(
                resource
                for resource in resources
                if resource.owner_module == normalized_owner
            )
        return resources
