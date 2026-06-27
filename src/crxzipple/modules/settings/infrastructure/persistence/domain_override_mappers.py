from __future__ import annotations

from crxzipple.modules.settings.domain.entities import SettingsOverride
from crxzipple.modules.settings.infrastructure.persistence.models import (
    SettingsOverrideModel,
)
from crxzipple.modules.settings.infrastructure.persistence.records import (
    SettingsOverrideRecord,
)


def override_record_from_domain(override: SettingsOverride) -> SettingsOverrideRecord:
    return SettingsOverrideRecord(
        override_id=override.id,
        resource_id=override.resource_id,
        resource_kind=override.resource_kind,
        override_kind="environment",
        scope_key=override.environment,
        priority=override.priority,
        status="active" if override.enabled else "disabled",
        override_payload=dict(override.values),
        source_kind="settings",
        reason=override.reason,
        actor=override.created_by,
        metadata=dict(override.metadata),
        created_at=override.created_at,
        updated_at=override.updated_at,
    )


def override_from_record(record: SettingsOverrideRecord) -> SettingsOverride:
    return SettingsOverride(
        id=record.override_id,
        resource_id=record.resource_id,
        resource_kind=record.resource_kind,
        environment=record.scope_key,
        values=record.override_payload,
        enabled=record.status == "active",
        priority=record.priority,
        reason=record.reason,
        created_by=record.actor,
        created_at=record.created_at,
        updated_at=record.updated_at,
        metadata=record.metadata,
    )


def apply_override_model(
    model: SettingsOverrideModel,
    stored: SettingsOverrideModel,
) -> None:
    model.resource_id = stored.resource_id
    model.resource_kind = stored.resource_kind
    model.override_kind = stored.override_kind
    model.scope_key = stored.scope_key
    model.priority = stored.priority
    model.status = stored.status
    model.override_payload = stored.override_payload
    model.source_kind = stored.source_kind
    model.source_ref = stored.source_ref
    model.reason = stored.reason
    model.actor = stored.actor
    model.expires_at = stored.expires_at
    model.redaction_policy = stored.redaction_policy
    model.metadata_ = stored.metadata_
    model.created_at = stored.created_at
    model.updated_at = stored.updated_at


__all__ = [
    "apply_override_model",
    "override_from_record",
    "override_record_from_domain",
]
