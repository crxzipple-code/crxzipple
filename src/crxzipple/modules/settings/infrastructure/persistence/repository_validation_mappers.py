from __future__ import annotations

from crxzipple.modules.settings.infrastructure.persistence.models import (
    SettingsValidationResultModel,
)
from crxzipple.modules.settings.infrastructure.persistence.records import (
    SettingsValidationResultRecord,
)
from crxzipple.modules.settings.infrastructure.persistence.repository_values import (
    _optional_text,
    _record_created_at,
    _required_text,
)
from crxzipple.shared.time import coerce_utc_datetime


def _validation_result_model(
    record: SettingsValidationResultRecord,
) -> SettingsValidationResultModel:
    return SettingsValidationResultModel(
        validation_id=_required_text(record.validation_id, "validation id"),
        resource_id=_required_text(record.resource_id, "resource id"),
        resource_kind=_required_text(record.resource_kind, "resource kind"),
        version_id=_optional_text(record.version_id),
        audit_id=_optional_text(record.audit_id),
        validator=_required_text(record.validator, "validator"),
        status=_required_text(record.status, "status"),
        valid=bool(record.valid),
        issues=[dict(issue) for issue in record.issues],
        checked_payload_digest=_optional_text(record.checked_payload_digest),
        redaction_policy=dict(record.redaction_policy),
        metadata_=dict(record.metadata),
        created_at=_record_created_at(record),
    )


def _validation_result_record(
    model: SettingsValidationResultModel,
) -> SettingsValidationResultRecord:
    return SettingsValidationResultRecord(
        validation_id=model.validation_id,
        resource_id=model.resource_id,
        resource_kind=model.resource_kind,
        version_id=model.version_id,
        audit_id=model.audit_id,
        validator=model.validator,
        status=model.status,
        valid=model.valid,
        issues=tuple(dict(issue) for issue in model.issues),
        checked_payload_digest=model.checked_payload_digest,
        redaction_policy=dict(model.redaction_policy),
        metadata=dict(model.metadata_),
        created_at=coerce_utc_datetime(model.created_at),
    )
