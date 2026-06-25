from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from crxzipple.modules.tool.application.catalog_models import (
    ToolFunctionCatalogRecord,
    ToolFunctionRequirements,
)
from crxzipple.modules.tool.domain.entities import ToolFunction
from crxzipple.modules.tool.domain.value_objects import (
    ToolFunctionRuntimeKind,
    ToolFunctionStatus,
)
from crxzipple.modules.tool.infrastructure.persistence.models import ToolFunctionModel
from crxzipple.modules.tool.infrastructure.persistence.repository_payloads import (
    credential_requirement_set_payload,
    credential_requirement_sets_from_payload,
    dict_payload,
    dict_tuple_payload,
    enum_filter_value,
    execution_support_from_payload,
    execution_support_to_payload,
    string_tuple_payload,
)
from crxzipple.shared.time import (
    coerce_optional_utc_datetime,
    coerce_utc_datetime,
)


class SqlAlchemyToolFunctionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._loaded_models: dict[str, ToolFunctionModel] = {}

    def upsert(self, function: ToolFunction) -> None:
        model = self._loaded_models.get(function.id)
        if model is None:
            model = self.session.get(ToolFunctionModel, function.id)
        if model is None:
            model = self._to_model(function)
            self.session.add(model)
        else:
            self._apply_to_model(model, function)
        self._loaded_models[function.id] = model

    def get(self, function_id: str) -> ToolFunction | None:
        model = self.session.get(ToolFunctionModel, function_id)
        if model is None:
            return None
        self._loaded_models[function_id] = model
        return self._to_entity(model)

    def list_by_ids(self, function_ids: tuple[str, ...]) -> dict[str, ToolFunction]:
        ordered_ids = tuple(dict.fromkeys(item for item in function_ids if item))
        if not ordered_ids:
            return {}
        models = self.session.scalars(
            select(ToolFunctionModel).where(
                ToolFunctionModel.function_id.in_(ordered_ids),
            ),
        ).all()
        result: dict[str, ToolFunction] = {}
        for model in models:
            self._loaded_models[model.function_id] = model
            result[model.function_id] = self._to_entity(model)
        return result

    def get_by_stable_key(self, stable_key: str) -> ToolFunction | None:
        model = self.session.scalars(
            select(ToolFunctionModel)
            .where(ToolFunctionModel.stable_key == stable_key)
            .limit(1),
        ).first()
        if model is None:
            return None
        self._loaded_models[model.function_id] = model
        return self._to_entity(model)

    def list(
        self,
        *,
        source_id: str | None = None,
        status: ToolFunctionStatus | str | None = None,
    ) -> list[ToolFunction]:
        statement = select(ToolFunctionModel)
        if source_id is not None:
            statement = statement.where(ToolFunctionModel.source_id == source_id)
        status_value = enum_filter_value(status)
        if status_value is not None:
            statement = statement.where(ToolFunctionModel.status == status_value)
        models = self.session.scalars(
            statement.order_by(ToolFunctionModel.updated_at.desc()),
        ).all()
        for model in models:
            self._loaded_models[model.function_id] = model
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_model(function: ToolFunction) -> ToolFunctionModel:
        return ToolFunctionModel(
            **SqlAlchemyToolFunctionRepository._to_mapping(function),
        )

    @staticmethod
    def _to_mapping(function: ToolFunction) -> dict[str, object]:
        return {
            "function_id": function.function_id,
            "source_id": function.source_id,
            "stable_key": function.stable_key,
            "name": function.name,
            "display_name": function.display_name,
            "description": function.description,
            "input_schema_payload": dict(function.input_schema),
            "runtime_kind": function.runtime_kind.value,
            "handler_ref_payload": dict(function.handler_ref),
            "capability_ids_payload": list(function.capability_ids),
            "credential_requirements_payload": [
                dict(requirement)
                for requirement in function.credential_requirements
            ],
            "access_requirement_sets_payload": [
                list(requirement_set)
                for requirement_set in function.access_requirement_sets
            ],
            "runtime_requirements_payload": [
                dict(requirement)
                for requirement in function.runtime_requirements
            ],
            "required_effect_ids_payload": list(function.required_effect_ids),
            "execution_support_payload": execution_support_to_payload(
                function.execution_support,
            ),
            "enabled": function.enabled,
            "trust_policy_payload": dict(function.trust_policy),
            "approval_policy_payload": dict(function.approval_policy),
            "credential_binding_overrides_payload": dict(
                function.credential_binding_overrides,
            ),
            "required_effect_overrides_payload": (
                list(function.required_effect_overrides)
                if function.required_effect_overrides is not None
                else None
            ),
            "metadata_payload": dict(function.metadata),
            "schema_hash": function.schema_hash,
            "status": function.status.value,
            "revision": function.revision,
            "created_at": function.created_at,
            "updated_at": function.updated_at,
            "last_seen_at": function.last_seen_at,
            "stale_since": function.stale_since,
            "deprecated_at": function.deprecated_at,
        }

    @staticmethod
    def _apply_to_model(
        model: ToolFunctionModel,
        function: ToolFunction,
    ) -> None:
        mapping = SqlAlchemyToolFunctionRepository._to_mapping(function)
        for key, value in mapping.items():
            setattr(model, key, value)

    @staticmethod
    def _to_entity(model: ToolFunctionModel) -> ToolFunction:
        return ToolFunction(
            id=model.function_id,
            source_id=model.source_id,
            stable_key=model.stable_key,
            name=model.name,
            display_name=model.display_name,
            description=model.description,
            input_schema=dict_payload(model.input_schema_payload),
            runtime_kind=ToolFunctionRuntimeKind(model.runtime_kind),
            handler_ref=dict_payload(model.handler_ref_payload),
            capability_ids=string_tuple_payload(model.capability_ids_payload),
            credential_requirements=dict_tuple_payload(
                model.credential_requirements_payload,
            ),
            access_requirement_sets=tuple(
                tuple(requirement_set)
                for requirement_set in model.access_requirement_sets_payload
                if isinstance(requirement_set, list | tuple)
            ),
            runtime_requirements=dict_tuple_payload(
                model.runtime_requirements_payload,
            ),
            required_effect_ids=string_tuple_payload(
                model.required_effect_ids_payload,
            ),
            execution_support=execution_support_from_payload(
                model.execution_support_payload,
            ),
            enabled=model.enabled,
            trust_policy=dict_payload(model.trust_policy_payload),
            approval_policy=dict_payload(model.approval_policy_payload),
            credential_binding_overrides={
                str(key): str(value)
                for key, value in dict_payload(
                    model.credential_binding_overrides_payload,
                ).items()
            },
            required_effect_overrides=(
                string_tuple_payload(model.required_effect_overrides_payload)
                if model.required_effect_overrides_payload is not None
                else None
            ),
            metadata=dict_payload(model.metadata_payload),
            schema_hash=model.schema_hash,
            status=ToolFunctionStatus(model.status),
            revision=model.revision,
            created_at=coerce_utc_datetime(model.created_at),
            updated_at=coerce_utc_datetime(model.updated_at),
            last_seen_at=coerce_optional_utc_datetime(model.last_seen_at),
            stale_since=coerce_optional_utc_datetime(model.stale_since),
            deprecated_at=coerce_optional_utc_datetime(model.deprecated_at),
        )


class SqlAlchemyToolFunctionCatalogRepository:
    def __init__(self, session: Session) -> None:
        self._functions = SqlAlchemyToolFunctionRepository(session)

    def list_by_source(self, source_id: str) -> tuple[ToolFunctionCatalogRecord, ...]:
        return tuple(
            _catalog_record_from_entity(function)
            for function in self._functions.list(source_id=source_id)
        )

    def add(self, function: ToolFunctionCatalogRecord) -> None:
        self._functions.upsert(_catalog_record_to_entity(function))

    def update(self, function: ToolFunctionCatalogRecord) -> None:
        self._functions.upsert(_catalog_record_to_entity(function))


def _catalog_record_to_entity(record: ToolFunctionCatalogRecord) -> ToolFunction:
    return ToolFunction(
        id=record.function_id,
        source_id=record.source_id,
        stable_key=record.stable_key,
        name=record.name,
        display_name=record.name,
        description=record.description,
        input_schema=dict(record.input_schema),
        runtime_kind=ToolFunctionRuntimeKind(record.runtime_kind.value),
        handler_ref={"ref": record.handler_ref},
        capability_ids=record.capabilities,
        credential_requirements=tuple(
            credential_requirement_set_payload(requirement_set)
            for requirement_set in record.requirements.credential_requirements
        ),
        access_requirement_sets=record.requirements.access_requirement_sets,
        runtime_requirements=tuple(
            {"requirements": list(requirement_set)}
            for requirement_set in record.requirements.runtime_requirement_sets
        ),
        required_effect_ids=record.requirements.required_effect_ids,
        enabled=record.enabled,
        trust_policy=dict(record.trust_policy),
        approval_policy=dict(record.approval_policy),
        credential_binding_overrides=dict(record.credential_binding_overrides),
        required_effect_overrides=record.required_effect_overrides,
        metadata=dict(record.metadata),
        schema_hash=record.schema_hash,
        status=ToolFunctionStatus(record.status.value),
        revision=record.revision,
        created_at=_record_datetime(
            record.created_at,
            record.updated_at,
            record.last_seen_at,
        ),
        updated_at=_record_datetime(
            record.updated_at,
            record.created_at,
            record.last_seen_at,
        ),
        last_seen_at=record.last_seen_at,
        stale_since=record.stale_since,
        deprecated_at=record.deprecated_at,
    )


def _catalog_record_from_entity(function: ToolFunction) -> ToolFunctionCatalogRecord:
    return ToolFunctionCatalogRecord(
        function_id=function.function_id,
        source_id=function.source_id,
        stable_key=function.stable_key,
        name=function.name,
        description=function.description,
        input_schema=function.input_schema,
        runtime_kind=function.runtime_kind.value,
        handler_ref=_handler_ref_from_payload(function.handler_ref),
        requirements=ToolFunctionRequirements(
            credential_requirements=credential_requirement_sets_from_payload(
                list(function.credential_requirements),
            ),
            access_requirement_sets=function.access_requirement_sets,
            runtime_requirement_sets=_runtime_requirement_sets_from_payload(
                function.runtime_requirements,
            ),
            required_effect_ids=function.required_effect_ids,
        ),
        capabilities=function.capability_ids,
        schema_hash=function.schema_hash,
        status=function.status.value,
        revision=function.revision,
        enabled=function.enabled,
        trust_policy=function.trust_policy,
        approval_policy=function.approval_policy,
        credential_binding_overrides=function.credential_binding_overrides,
        required_effect_overrides=function.required_effect_overrides,
        metadata=function.metadata,
        created_at=function.created_at,
        updated_at=function.updated_at,
        last_seen_at=function.last_seen_at,
        stale_since=function.stale_since,
        deprecated_at=function.deprecated_at,
    )


def _handler_ref_from_payload(payload: dict[str, Any]) -> str:
    for key in ("ref", "handler", "runtime_key"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _record_datetime(*values: datetime | None) -> datetime:
    for value in values:
        if value is not None:
            return value
    return datetime.now(timezone.utc)


def _runtime_requirement_sets_from_payload(
    payload: tuple[dict[str, Any], ...],
) -> tuple[tuple[str, ...], ...]:
    requirement_sets: list[tuple[str, ...]] = []
    for item in payload:
        raw_requirements = item.get("requirements")
        if not isinstance(raw_requirements, list | tuple):
            continue
        normalized = tuple(
            dict.fromkeys(
                str(requirement).strip()
                for requirement in raw_requirements
                if str(requirement).strip()
            ),
        )
        if normalized:
            requirement_sets.append(normalized)
    return tuple(requirement_sets)
