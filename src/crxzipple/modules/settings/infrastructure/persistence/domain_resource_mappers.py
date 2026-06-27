from __future__ import annotations

from crxzipple.modules.settings.domain.entities import SettingsResource
from crxzipple.modules.settings.infrastructure.persistence.records import (
    SettingsResourceRecord,
)


def resource_record_from_domain(resource: SettingsResource) -> SettingsResourceRecord:
    metadata = dict(resource.metadata)
    owner_module = str(metadata.get("owner_module") or resource.owner_module)
    metadata["owner_module"] = owner_module
    return SettingsResourceRecord(
        resource_id=resource.id,
        resource_kind=resource.resource_kind,
        governance_scope=resource.scope,
        config_contract=dict(
            metadata.get("config_contract")
            if isinstance(metadata.get("config_contract"), dict)
            else {"resource_kind": resource.resource_kind}
        ),
        storage_key=str(
            metadata.get("storage_key")
            or f"settings://{resource.resource_kind}/{resource.id}"
        ),
        display_name=resource.display_name,
        consumer_modules=tuple(
            metadata.get("consumer_modules")
            if isinstance(metadata.get("consumer_modules"), tuple)
            else tuple(metadata.get("consumer_modules") or (owner_module,))
        ),
        status=resource.status.value,
        published_version_id=resource.active_version_id,
        metadata=metadata,
        created_at=resource.created_at,
        updated_at=resource.updated_at,
    )


def resource_from_record(record: SettingsResourceRecord) -> SettingsResource:
    metadata = dict(record.metadata)
    owner_module = str(
        metadata.get("owner_module")
        or next(iter(record.consumer_modules), None)
        or "settings"
    )
    return SettingsResource(
        id=record.resource_id,
        resource_kind=record.resource_kind,
        owner_module=owner_module,
        scope=record.governance_scope,
        display_name=record.display_name,
        status=record.status,
        active_version_id=record.published_version_id,
        metadata=metadata,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


__all__ = ["resource_from_record", "resource_record_from_domain"]
