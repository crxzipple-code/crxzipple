from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from crxzipple.modules.tool.application.catalog_models import (
    ToolSourceDiscoveryRunRecord,
)
from crxzipple.modules.tool.domain.entities import ToolSource
from crxzipple.modules.tool.domain.value_objects import (
    ToolCatalogSourceKind,
    ToolSourceStatus,
)
from crxzipple.modules.tool.infrastructure.persistence.models import (
    ToolSourceDiscoveryRunModel,
    ToolSourceModel,
)
from crxzipple.modules.tool.infrastructure.persistence.repository_payloads import (
    dict_payload,
    dict_tuple_payload,
    enum_filter_value,
)
from crxzipple.shared.time import (
    coerce_optional_utc_datetime,
    coerce_utc_datetime,
)


class SqlAlchemyToolSourceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._loaded_models: dict[str, ToolSourceModel] = {}

    def upsert(self, source: ToolSource) -> None:
        model = self._loaded_models.get(source.id)
        if model is None:
            model = self.session.get(ToolSourceModel, source.id)
        if model is None:
            model = self._to_model(source)
            self.session.add(model)
        else:
            self._apply_to_model(model, source)
        self._loaded_models[source.id] = model

    def get(self, source_id: str) -> ToolSource | None:
        model = self.session.get(ToolSourceModel, source_id)
        if model is None:
            return None
        self._loaded_models[source_id] = model
        return self._to_entity(model)

    def list_by_ids(self, source_ids: tuple[str, ...]) -> dict[str, ToolSource]:
        ordered_ids = tuple(dict.fromkeys(item for item in source_ids if item))
        if not ordered_ids:
            return {}
        models = self.session.scalars(
            select(ToolSourceModel).where(ToolSourceModel.source_id.in_(ordered_ids)),
        ).all()
        result: dict[str, ToolSource] = {}
        for model in models:
            self._loaded_models[model.source_id] = model
            result[model.source_id] = self._to_entity(model)
        return result

    def list(
        self,
        *,
        kind: ToolCatalogSourceKind | str | None = None,
        status: ToolSourceStatus | str | None = None,
    ) -> list[ToolSource]:
        statement = select(ToolSourceModel)
        kind_value = enum_filter_value(kind)
        if kind_value is not None:
            statement = statement.where(ToolSourceModel.kind == kind_value)
        status_value = enum_filter_value(status)
        if status_value is not None:
            statement = statement.where(ToolSourceModel.status == status_value)
        models = self.session.scalars(
            statement.order_by(ToolSourceModel.updated_at.desc()),
        ).all()
        for model in models:
            self._loaded_models[model.source_id] = model
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_model(source: ToolSource) -> ToolSourceModel:
        return ToolSourceModel(**SqlAlchemyToolSourceRepository._to_mapping(source))

    @staticmethod
    def _to_mapping(source: ToolSource) -> dict[str, object]:
        return {
            "source_id": source.source_id,
            "kind": source.kind.value,
            "display_name": source.display_name,
            "description": source.description,
            "config_payload": dict(source.config),
            "credential_requirements_payload": [
                dict(requirement)
                for requirement in source.credential_requirements
            ],
            "runtime_requirements_payload": [
                dict(requirement)
                for requirement in source.runtime_requirements
            ],
            "status": source.status.value,
            "revision": source.revision,
            "config_hash": source.config_hash,
            "last_discovered_at": source.last_discovered_at,
            "last_discovery_status": source.last_discovery_status,
            "created_at": source.created_at,
            "updated_at": source.updated_at,
        }

    @staticmethod
    def _apply_to_model(model: ToolSourceModel, source: ToolSource) -> None:
        mapping = SqlAlchemyToolSourceRepository._to_mapping(source)
        for key, value in mapping.items():
            setattr(model, key, value)

    @staticmethod
    def _to_entity(model: ToolSourceModel) -> ToolSource:
        return ToolSource(
            id=model.source_id,
            kind=ToolCatalogSourceKind(model.kind),
            display_name=model.display_name,
            description=model.description,
            config=dict_payload(model.config_payload),
            credential_requirements=dict_tuple_payload(
                model.credential_requirements_payload,
            ),
            runtime_requirements=dict_tuple_payload(
                model.runtime_requirements_payload,
            ),
            status=ToolSourceStatus(model.status),
            revision=model.revision,
            config_hash=model.config_hash,
            last_discovered_at=coerce_optional_utc_datetime(
                model.last_discovered_at,
            ),
            last_discovery_status=model.last_discovery_status,
            created_at=coerce_utc_datetime(model.created_at),
            updated_at=coerce_utc_datetime(model.updated_at),
        )


class SqlAlchemyToolSourceDiscoveryRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, record: ToolSourceDiscoveryRunRecord) -> None:
        self.session.add(self._to_model(record))

    def list_by_source(
        self,
        source_id: str,
        *,
        limit: int = 20,
    ) -> tuple[ToolSourceDiscoveryRunRecord, ...]:
        bounded_limit = max(1, min(int(limit), 200))
        models = self.session.scalars(
            select(ToolSourceDiscoveryRunModel)
            .where(ToolSourceDiscoveryRunModel.source_id == source_id)
            .order_by(ToolSourceDiscoveryRunModel.discovered_at.desc())
            .limit(bounded_limit),
        ).all()
        return tuple(self._to_record(model) for model in models)

    @staticmethod
    def _to_model(
        record: ToolSourceDiscoveryRunRecord,
    ) -> ToolSourceDiscoveryRunModel:
        return ToolSourceDiscoveryRunModel(
            discovery_run_id=record.discovery_run_id,
            source_id=record.source_id,
            source_revision=record.source_revision,
            config_hash=record.config_hash,
            status=record.status.value,
            discovered_at=record.discovered_at,
            function_count=record.function_count,
            provider_backend_count=record.provider_backend_count,
            error_message=record.error_message,
            metadata_payload=dict(record.metadata),
        )

    @staticmethod
    def _to_record(
        model: ToolSourceDiscoveryRunModel,
    ) -> ToolSourceDiscoveryRunRecord:
        return ToolSourceDiscoveryRunRecord(
            discovery_run_id=model.discovery_run_id,
            source_id=model.source_id,
            source_revision=model.source_revision,
            config_hash=model.config_hash,
            status=model.status,
            discovered_at=coerce_utc_datetime(model.discovered_at),
            function_count=model.function_count,
            provider_backend_count=model.provider_backend_count,
            error_message=model.error_message,
            metadata=dict_payload(model.metadata_payload),
        )
