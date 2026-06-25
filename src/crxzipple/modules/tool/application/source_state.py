from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.tool.application.catalog_models import (
    ToolSourceCatalogRecord,
    ToolSourceDiscoveryResult,
)
from crxzipple.modules.tool.application.source_record_mapping import (
    source_record_to_entity,
    stable_payload,
)
from crxzipple.modules.tool.domain.entities import ToolSource
from crxzipple.modules.tool.domain.value_objects import ToolSourceStatus


def merge_source(
    *,
    incoming: ToolSourceCatalogRecord,
    existing: ToolSource | None,
    discovery: ToolSourceDiscoveryResult | None = None,
    observed_at: datetime,
) -> ToolSource:
    incoming_entity = source_record_to_entity(
        incoming,
        observed_at=observed_at,
        discovery=discovery,
    )
    if existing is None:
        return incoming_entity

    status = existing.status
    if status not in {ToolSourceStatus.DISABLED, ToolSourceStatus.DELETED}:
        status = incoming_entity.status

    changed = source_config_changed(existing, incoming_entity)
    discovery_changed = discovery is not None and (
        existing.last_discovered_at != incoming_entity.last_discovered_at
        or existing.last_discovery_status != incoming_entity.last_discovery_status
        or existing.status != status
    )
    revision = existing.revision + 1 if changed or discovery_changed else existing.revision
    updated_at = observed_at if changed or discovery_changed else existing.updated_at
    return ToolSource(
        id=existing.source_id,
        kind=incoming_entity.kind,
        display_name=incoming_entity.display_name,
        description=incoming_entity.description,
        config=incoming_entity.config,
        credential_requirements=incoming_entity.credential_requirements,
        runtime_requirements=incoming_entity.runtime_requirements,
        status=status,
        revision=revision,
        config_hash=incoming_entity.config_hash,
        last_discovered_at=incoming_entity.last_discovered_at,
        last_discovery_status=incoming_entity.last_discovery_status,
        created_at=existing.created_at,
        updated_at=updated_at,
    )


def source_config_changed(existing: ToolSource, incoming: ToolSource) -> bool:
    return any(
        (
            existing.kind != incoming.kind,
            existing.display_name != incoming.display_name,
            existing.description != incoming.description,
            existing.config_hash != incoming.config_hash,
            existing.config != incoming.config,
            existing.credential_requirements != incoming.credential_requirements,
            existing.runtime_requirements != incoming.runtime_requirements,
        ),
    )


def source_changed(existing: ToolSource, incoming: ToolSource) -> bool:
    return source_config_changed(existing, incoming) or any(
        (
            existing.status != incoming.status,
            existing.last_discovered_at != incoming.last_discovered_at,
            existing.last_discovery_status != incoming.last_discovery_status,
        ),
    )


def source_changed_fields(
    existing: ToolSource | None,
    incoming: ToolSource,
) -> tuple[str, ...]:
    if existing is None:
        return ()
    comparisons: tuple[tuple[str, Any, Any], ...] = (
        ("kind", existing.kind, incoming.kind),
        ("display_name", existing.display_name, incoming.display_name),
        ("description", existing.description, incoming.description),
        ("config", existing.config, incoming.config),
        (
            "credential_requirements",
            existing.credential_requirements,
            incoming.credential_requirements,
        ),
        ("runtime_requirements", existing.runtime_requirements, incoming.runtime_requirements),
        ("status", existing.status, incoming.status),
        ("config_hash", existing.config_hash, incoming.config_hash),
        ("last_discovered_at", existing.last_discovered_at, incoming.last_discovered_at),
        (
            "last_discovery_status",
            existing.last_discovery_status,
            incoming.last_discovery_status,
        ),
    )
    return tuple(
        field_name
        for field_name, current, next_value in comparisons
        if stable_payload(current) != stable_payload(next_value)
    )


__all__ = [
    "merge_source",
    "source_changed",
    "source_changed_fields",
]
