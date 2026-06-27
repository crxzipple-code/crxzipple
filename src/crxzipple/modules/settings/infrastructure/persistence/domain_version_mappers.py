from __future__ import annotations

from crxzipple.modules.settings.domain.entities import SettingsResourceVersion
from crxzipple.modules.settings.domain.value_objects import SettingsValidationResult
from crxzipple.modules.settings.infrastructure.persistence.models import (
    SettingsResourceModel,
    SettingsResourceVersionModel,
)
from crxzipple.modules.settings.infrastructure.persistence.records import (
    SettingsResourceVersionRecord,
)


def version_record_from_domain(
    version: SettingsResourceVersion,
) -> SettingsResourceVersionRecord:
    metadata = dict(version.metadata)
    metadata["validation"] = version.validation.to_payload()
    return SettingsResourceVersionRecord(
        version_id=version.id,
        resource_id=version.resource_id,
        resource_kind=version.resource_kind,
        version_number=version.version_number,
        payload=dict(version.payload),
        status=version.status.value,
        source_kind=version.source,
        created_by=version.created_by,
        reason=version.reason,
        published_at=version.published_at,
        metadata=metadata,
        created_at=version.created_at,
        updated_at=version.published_at or version.created_at,
    )


def version_from_record(
    record: SettingsResourceVersionRecord,
) -> SettingsResourceVersion:
    validation_payload = record.metadata.get("validation")
    validation = (
        SettingsValidationResult.from_payload(validation_payload)
        if isinstance(validation_payload, dict)
        else SettingsValidationResult(ok=record.status != "failed_validation")
    )
    return SettingsResourceVersion(
        id=record.version_id,
        resource_id=record.resource_id,
        resource_kind=record.resource_kind,
        payload=record.payload,
        version_number=record.version_number,
        status=record.status,
        validation=validation,
        source=record.source_kind,
        reason=record.reason,
        created_by=record.created_by,
        created_at=record.created_at,
        published_at=record.published_at,
        metadata=record.metadata,
    )


def apply_version_model(
    model: SettingsResourceVersionModel,
    stored: SettingsResourceVersionModel,
) -> None:
    model.resource_id = stored.resource_id
    model.resource_kind = stored.resource_kind
    model.version_number = stored.version_number
    model.status = stored.status
    model.payload = stored.payload
    model.source_kind = stored.source_kind
    model.source_ref = stored.source_ref
    model.source_metadata = stored.source_metadata
    model.contract_version = stored.contract_version
    model.redaction_policy = stored.redaction_policy
    model.validation_result_id = stored.validation_result_id
    model.created_by = stored.created_by
    model.reason = stored.reason
    model.published_at = stored.published_at
    model.metadata_ = stored.metadata_
    model.created_at = stored.created_at
    model.updated_at = stored.updated_at


def apply_version_to_resource(
    resource: SettingsResourceModel,
    version: SettingsResourceVersionModel,
) -> None:
    latest = resource.latest_version_number
    if latest is None or version.version_number > latest:
        resource.latest_version_number = version.version_number
    if version.status == "published":
        resource.published_version_id = version.version_id
        resource.published_version_number = version.version_number
        resource.updated_at = version.updated_at


__all__ = [
    "apply_version_model",
    "apply_version_to_resource",
    "version_from_record",
    "version_record_from_domain",
]
