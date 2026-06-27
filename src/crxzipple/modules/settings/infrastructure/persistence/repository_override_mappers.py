from __future__ import annotations

from crxzipple.modules.settings.infrastructure.persistence.models import (
    SettingsOverrideModel,
)
from crxzipple.modules.settings.infrastructure.persistence.records import (
    SettingsOverrideRecord,
)
from crxzipple.modules.settings.infrastructure.persistence.repository_values import (
    _optional_text,
    _record_created_at,
    _record_updated_at,
    _required_text,
)
from crxzipple.shared.time import coerce_optional_utc_datetime, coerce_utc_datetime


def _override_model(record: SettingsOverrideRecord) -> SettingsOverrideModel:
    return SettingsOverrideModel(
        override_id=_required_text(record.override_id, "override id"),
        resource_id=_required_text(record.resource_id, "resource id"),
        resource_kind=_required_text(record.resource_kind, "resource kind"),
        override_kind=_required_text(record.override_kind, "override kind"),
        scope_key=_required_text(record.scope_key, "scope key"),
        priority=int(record.priority),
        status=_required_text(record.status, "status"),
        override_payload=dict(record.override_payload),
        source_kind=_required_text(record.source_kind, "source kind"),
        source_ref=_optional_text(record.source_ref),
        reason=_optional_text(record.reason),
        actor=_optional_text(record.actor),
        expires_at=coerce_optional_utc_datetime(record.expires_at),
        redaction_policy=dict(record.redaction_policy),
        metadata_=dict(record.metadata),
        created_at=_record_created_at(record),
        updated_at=_record_updated_at(record),
    )


def _override_record(model: SettingsOverrideModel) -> SettingsOverrideRecord:
    return SettingsOverrideRecord(
        override_id=model.override_id,
        resource_id=model.resource_id,
        resource_kind=model.resource_kind,
        override_kind=model.override_kind,
        scope_key=model.scope_key,
        priority=model.priority,
        status=model.status,
        override_payload=dict(model.override_payload),
        source_kind=model.source_kind,
        source_ref=model.source_ref,
        reason=model.reason,
        actor=model.actor,
        expires_at=coerce_optional_utc_datetime(model.expires_at),
        redaction_policy=dict(model.redaction_policy),
        metadata=dict(model.metadata_),
        created_at=coerce_utc_datetime(model.created_at),
        updated_at=coerce_utc_datetime(model.updated_at),
    )
