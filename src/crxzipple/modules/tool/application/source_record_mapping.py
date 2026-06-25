from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from crxzipple.modules.tool.application.catalog_models import (
    ToolFunctionCatalogRecord,
    ToolFunctionRequirements,
    ToolProviderBackendCandidate,
    ToolSourceCatalogKind,
    ToolSourceCatalogRecord,
    ToolSourceDiscoveryResult,
    ToolSourceDiscoveryStatus,
    ToolSourceStatus as CatalogToolSourceStatus,
)
from crxzipple.modules.tool.application.source_requirements import (
    credential_requirement_sets_from_payload,
    runtime_requirement_sets_from_payload,
)
from crxzipple.modules.tool.domain.entities import ToolProviderBackend, ToolSource
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.domain.value_objects import (
    ToolCatalogSourceKind,
    ToolFunctionRuntimeKind as DomainToolFunctionRuntimeKind,
    ToolProviderBackendStatus,
    ToolProviderCapability,
    ToolSourceStatus,
)


def provider_backend_candidate_to_entity(
    candidate: ToolProviderBackendCandidate,
    *,
    existing: ToolProviderBackend | None,
    observed_at: datetime,
) -> ToolProviderBackend:
    status = ToolProviderBackendStatus.ACTIVE
    enabled = candidate.enabled
    created_at = observed_at
    if existing is not None:
        created_at = existing.created_at
        enabled = existing.enabled
        status = (
            existing.status
            if existing.status
            in {ToolProviderBackendStatus.DISABLED, ToolProviderBackendStatus.DELETED}
            else ToolProviderBackendStatus.ACTIVE
        )
    return ToolProviderBackend(
        id=candidate.backend_id,
        source_id=candidate.source_id,
        capability=ToolProviderCapability(candidate.capability),
        display_name=candidate.display_name,
        credential_requirements=tuple(
            stable_payload(requirement)
            for requirement in candidate.requirements.credential_requirements
        ),
        runtime_ref={
            "runtime_kind": DomainToolFunctionRuntimeKind(
                candidate.runtime_kind,
            ).value,
            "ref": candidate.runtime_ref,
            "metadata": stable_payload(candidate.metadata),
        },
        priority=candidate.priority,
        enabled=enabled,
        status=status,
        created_at=created_at,
        updated_at=observed_at,
    )


def source_record_to_entity(
    record: ToolSourceCatalogRecord,
    *,
    observed_at: datetime,
    discovery: ToolSourceDiscoveryResult | None = None,
) -> ToolSource:
    status = domain_source_status(record.status)
    if discovery is not None and discovery.status is ToolSourceDiscoveryStatus.FAILED:
        status = ToolSourceStatus.ERROR
    return ToolSource(
        id=record.source_id,
        kind=domain_source_kind(record.kind),
        display_name=record.display_name,
        description=record.description,
        config=dict(record.config),
        credential_requirements=tuple(
            stable_payload(requirement)
            for requirement in record.credential_requirements
        ),
        runtime_requirements=tuple(
            {"requirement": requirement}
            for requirement in record.runtime_requirements
        ),
        status=status,
        revision=record.revision,
        config_hash=record.config_hash,
        last_discovered_at=(
            discovery.discovered_at
            if discovery is not None
            else record.last_discovered_at
        ),
        last_discovery_status=(
            discovery.status.value
            if discovery is not None
            else (
                record.last_discovery_status.value
                if isinstance(record.last_discovery_status, ToolSourceDiscoveryStatus)
                else record.last_discovery_status
            )
        ),
        created_at=record.created_at or observed_at,
        updated_at=record.updated_at or observed_at,
    )


def source_entity_to_record(source: ToolSource) -> ToolSourceCatalogRecord:
    return ToolSourceCatalogRecord(
        source_id=source.source_id,
        kind=ToolSourceCatalogKind(source.kind.value),
        display_name=source.display_name,
        description=source.description,
        config=dict(source.config),
        credential_requirements=tuple(source.credential_requirements),  # type: ignore[arg-type]
        runtime_requirements=tuple(
            str(item.get("requirement", "")).strip()
            for item in source.runtime_requirements
            if str(item.get("requirement", "")).strip()
        ),
        status=CatalogToolSourceStatus(source.status.value),
        revision=source.revision,
        config_hash=source.config_hash,
        last_discovered_at=source.last_discovered_at,
        last_discovery_status=(
            ToolSourceDiscoveryStatus(source.last_discovery_status)
            if source.last_discovery_status
            and source.last_discovery_status
            in {status.value for status in ToolSourceDiscoveryStatus}
            else None
        ),
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


def function_entity_to_record(function: Any) -> ToolFunctionCatalogRecord:
    return ToolFunctionCatalogRecord(
        function_id=function.function_id,
        source_id=function.source_id,
        stable_key=function.stable_key,
        name=function.name,
        description=function.description,
        input_schema=dict(function.input_schema),
        runtime_kind=function.runtime_kind.value,
        handler_ref=handler_ref_from_payload(function.handler_ref),
        requirements=ToolFunctionRequirements(
            credential_requirements=credential_requirement_sets_from_payload(
                function.credential_requirements,
            ),
            access_requirement_sets=function.access_requirement_sets,
            runtime_requirement_sets=runtime_requirement_sets_from_payload(
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


def handler_ref_from_payload(payload: Mapping[str, Any]) -> str:
    for key in ("ref", "handler", "runtime_key"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def domain_source_kind(value: ToolSourceCatalogKind | str) -> ToolCatalogSourceKind:
    kind = ToolSourceCatalogKind(str(value))
    try:
        return ToolCatalogSourceKind(kind.value)
    except ValueError as exc:
        raise ToolValidationError(
            f"Tool source kind '{kind.value}' is not supported by the persistent catalog.",
        ) from exc


def domain_source_status(
    value: CatalogToolSourceStatus | str,
) -> ToolSourceStatus:
    return ToolSourceStatus(CatalogToolSourceStatus(str(value)).value)


def stable_payload(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: stable_payload(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): stable_payload(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, tuple | list):
        return [stable_payload(item) for item in value]
    return value


__all__ = [
    "domain_source_kind",
    "domain_source_status",
    "function_entity_to_record",
    "handler_ref_from_payload",
    "provider_backend_candidate_to_entity",
    "source_entity_to_record",
    "source_record_to_entity",
    "stable_payload",
]
