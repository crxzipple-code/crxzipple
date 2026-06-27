from __future__ import annotations

from crxzipple.modules.settings.infrastructure.persistence.models import (
    SettingsEffectiveSnapshotModel,
)
from crxzipple.modules.settings.infrastructure.persistence.records import (
    SettingsEffectiveSnapshotRecord,
)
from crxzipple.modules.settings.infrastructure.persistence.repository_values import (
    _optional_text,
    _record_created_at,
    _record_generated_at,
    _record_updated_at,
    _required_text,
)
from crxzipple.shared.time import coerce_utc_datetime


def _snapshot_model(
    record: SettingsEffectiveSnapshotRecord,
) -> SettingsEffectiveSnapshotModel:
    return SettingsEffectiveSnapshotModel(
        snapshot_id=_required_text(record.snapshot_id, "snapshot id"),
        resource_id=_required_text(record.resource_id, "resource id"),
        resource_kind=_required_text(record.resource_kind, "resource kind"),
        scope_key=_required_text(record.scope_key, "scope key"),
        version_id=_optional_text(record.version_id),
        version_number=record.version_number,
        effective_payload=dict(record.effective_payload),
        resolution_trace=[dict(item) for item in record.resolution_trace],
        sources=[dict(item) for item in record.sources],
        overrides_applied=[dict(item) for item in record.overrides_applied],
        status=_required_text(record.status, "status"),
        is_current=bool(record.is_current),
        generated_at=_record_generated_at(record),
        metadata_=dict(record.metadata),
        created_at=_record_created_at(record),
        updated_at=_record_updated_at(record),
    )


def _snapshot_record(
    model: SettingsEffectiveSnapshotModel,
) -> SettingsEffectiveSnapshotRecord:
    return SettingsEffectiveSnapshotRecord(
        snapshot_id=model.snapshot_id,
        resource_id=model.resource_id,
        resource_kind=model.resource_kind,
        scope_key=model.scope_key,
        version_id=model.version_id,
        version_number=model.version_number,
        effective_payload=dict(model.effective_payload),
        resolution_trace=tuple(dict(item) for item in model.resolution_trace),
        sources=tuple(dict(item) for item in model.sources),
        overrides_applied=tuple(dict(item) for item in model.overrides_applied),
        status=model.status,
        is_current=model.is_current,
        generated_at=coerce_utc_datetime(model.generated_at),
        metadata=dict(model.metadata_),
        created_at=coerce_utc_datetime(model.created_at),
        updated_at=coerce_utc_datetime(model.updated_at),
    )
