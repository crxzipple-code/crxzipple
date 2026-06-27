from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

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
from crxzipple.modules.tool.infrastructure.persistence.function_repository import (
    SqlAlchemyToolFunctionRepository,
)
from crxzipple.modules.tool.infrastructure.persistence.repository_payloads import (
    credential_requirement_set_payload,
    credential_requirement_sets_from_payload,
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
