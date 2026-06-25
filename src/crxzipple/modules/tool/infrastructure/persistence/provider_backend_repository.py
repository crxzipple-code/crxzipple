from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from crxzipple.modules.tool.domain.entities import ToolProviderBackend
from crxzipple.modules.tool.domain.value_objects import (
    ToolProviderBackendStatus,
    ToolProviderCapability,
)
from crxzipple.modules.tool.infrastructure.persistence.models import (
    ToolProviderBackendModel,
)
from crxzipple.modules.tool.infrastructure.persistence.repository_payloads import (
    dict_payload,
    dict_tuple_payload,
    enum_filter_value,
)
from crxzipple.shared.time import coerce_utc_datetime


class SqlAlchemyToolProviderBackendRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._loaded_models: dict[str, ToolProviderBackendModel] = {}

    def upsert(self, backend: ToolProviderBackend) -> None:
        model = self._loaded_models.get(backend.id)
        if model is None:
            model = self.session.get(ToolProviderBackendModel, backend.id)
        if model is None:
            model = self._to_model(backend)
            self.session.add(model)
        else:
            self._apply_to_model(model, backend)
        self._loaded_models[backend.id] = model

    def get(self, backend_id: str) -> ToolProviderBackend | None:
        model = self.session.get(ToolProviderBackendModel, backend_id)
        if model is None:
            return None
        self._loaded_models[backend_id] = model
        return self._to_entity(model)

    def list(
        self,
        *,
        source_id: str | None = None,
        capability: ToolProviderCapability | str | None = None,
        status: ToolProviderBackendStatus | str | None = None,
    ) -> list[ToolProviderBackend]:
        statement = select(ToolProviderBackendModel)
        if source_id is not None:
            statement = statement.where(ToolProviderBackendModel.source_id == source_id)
        capability_value = enum_filter_value(capability)
        if capability_value is not None:
            statement = statement.where(
                ToolProviderBackendModel.capability == capability_value,
            )
        status_value = enum_filter_value(status)
        if status_value is not None:
            statement = statement.where(ToolProviderBackendModel.status == status_value)
        models = self.session.scalars(
            statement.order_by(
                ToolProviderBackendModel.priority.asc(),
                ToolProviderBackendModel.updated_at.desc(),
            ),
        ).all()
        for model in models:
            self._loaded_models[model.backend_id] = model
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_model(backend: ToolProviderBackend) -> ToolProviderBackendModel:
        return ToolProviderBackendModel(
            **SqlAlchemyToolProviderBackendRepository._to_mapping(backend),
        )

    @staticmethod
    def _to_mapping(backend: ToolProviderBackend) -> dict[str, object]:
        return {
            "backend_id": backend.backend_id,
            "source_id": backend.source_id,
            "capability": backend.capability.value,
            "display_name": backend.display_name,
            "credential_requirements_payload": [
                dict(requirement)
                for requirement in backend.credential_requirements
            ],
            "runtime_ref_payload": dict(backend.runtime_ref),
            "priority": backend.priority,
            "enabled": backend.enabled,
            "status": backend.status.value,
            "created_at": backend.created_at,
            "updated_at": backend.updated_at,
        }

    @staticmethod
    def _apply_to_model(
        model: ToolProviderBackendModel,
        backend: ToolProviderBackend,
    ) -> None:
        mapping = SqlAlchemyToolProviderBackendRepository._to_mapping(backend)
        for key, value in mapping.items():
            setattr(model, key, value)

    @staticmethod
    def _to_entity(model: ToolProviderBackendModel) -> ToolProviderBackend:
        return ToolProviderBackend(
            id=model.backend_id,
            source_id=model.source_id,
            capability=ToolProviderCapability(model.capability),
            display_name=model.display_name,
            credential_requirements=dict_tuple_payload(
                model.credential_requirements_payload,
            ),
            runtime_ref=dict_payload(model.runtime_ref_payload),
            priority=model.priority,
            enabled=model.enabled,
            status=ToolProviderBackendStatus(model.status),
            created_at=coerce_utc_datetime(model.created_at),
            updated_at=coerce_utc_datetime(model.updated_at),
        )
