from __future__ import annotations

from crxzipple.modules.settings.infrastructure.persistence.models import (
    SettingsResourceVersionModel,
)
from crxzipple.modules.settings.infrastructure.persistence.records import (
    SettingsResourceVersionRecord,
)
from crxzipple.modules.settings.infrastructure.persistence.repository_values import (
    _optional_text,
    _record_created_at,
    _record_updated_at,
    _required_text,
)
from crxzipple.shared.time import coerce_optional_utc_datetime, coerce_utc_datetime


def _version_model(
    record: SettingsResourceVersionRecord,
) -> SettingsResourceVersionModel:
    return SettingsResourceVersionModel(
        version_id=_required_text(record.version_id, "version id"),
        resource_id=_required_text(record.resource_id, "resource id"),
        resource_kind=_required_text(record.resource_kind, "resource kind"),
        version_number=int(record.version_number),
        status=_required_text(record.status, "status"),
        payload=dict(record.payload),
        source_kind=_required_text(record.source_kind, "source kind"),
        source_ref=_optional_text(record.source_ref),
        source_metadata=dict(record.source_metadata),
        contract_version=_optional_text(record.contract_version),
        redaction_policy=dict(record.redaction_policy),
        validation_result_id=_optional_text(record.validation_result_id),
        created_by=_optional_text(record.created_by),
        reason=_optional_text(record.reason),
        published_at=coerce_optional_utc_datetime(record.published_at),
        metadata_=dict(record.metadata),
        created_at=_record_created_at(record),
        updated_at=_record_updated_at(record),
    )


def _version_record(
    model: SettingsResourceVersionModel,
) -> SettingsResourceVersionRecord:
    return SettingsResourceVersionRecord(
        version_id=model.version_id,
        resource_id=model.resource_id,
        resource_kind=model.resource_kind,
        version_number=model.version_number,
        status=model.status,
        payload=dict(model.payload),
        source_kind=model.source_kind,
        source_ref=model.source_ref,
        source_metadata=dict(model.source_metadata),
        contract_version=model.contract_version,
        redaction_policy=dict(model.redaction_policy),
        validation_result_id=model.validation_result_id,
        created_by=model.created_by,
        reason=model.reason,
        published_at=coerce_optional_utc_datetime(model.published_at),
        metadata=dict(model.metadata_),
        created_at=coerce_utc_datetime(model.created_at),
        updated_at=coerce_utc_datetime(model.updated_at),
    )
