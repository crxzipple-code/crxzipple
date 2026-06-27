from __future__ import annotations

from crxzipple.modules.settings.domain.entities import SettingsEffectiveSnapshot
from crxzipple.modules.settings.domain.value_objects import SettingsValidationResult
from crxzipple.modules.settings.infrastructure.persistence.records import (
    SettingsEffectiveSnapshotRecord,
)
from crxzipple.shared.settings import ConfigSource, SettingsResourceRef


def snapshot_record_from_domain(
    snapshot: SettingsEffectiveSnapshot,
) -> SettingsEffectiveSnapshotRecord:
    version_number = _version_number_from_sources(snapshot.sources)
    metadata = dict(snapshot.metadata)
    metadata["resource"] = snapshot.resource.to_payload()
    metadata["validation"] = snapshot.validation.to_payload()
    return SettingsEffectiveSnapshotRecord(
        snapshot_id=snapshot.id,
        resource_id=snapshot.resource.resource_id,
        resource_kind=snapshot.resource.resource_kind,
        scope_key=snapshot.environment or "default",
        version_id=snapshot.version_id,
        version_number=version_number,
        effective_payload=dict(snapshot.effective_value),
        sources=tuple(source.to_payload() for source in snapshot.sources),
        overrides_applied=tuple(source.to_payload() for source in snapshot.overrides),
        metadata=metadata,
        created_at=snapshot.created_at,
        generated_at=snapshot.created_at,
    )


def snapshot_from_record(
    record: SettingsEffectiveSnapshotRecord,
) -> SettingsEffectiveSnapshot:
    resource_payload = record.metadata.get("resource")
    resource = (
        SettingsResourceRef.from_payload(resource_payload)
        if isinstance(resource_payload, dict)
        else SettingsResourceRef(
            resource_id=record.resource_id,
            resource_kind=record.resource_kind,
        )
    )
    validation_payload = record.metadata.get("validation")
    validation = (
        SettingsValidationResult.from_payload(validation_payload)
        if isinstance(validation_payload, dict)
        else SettingsValidationResult.ok_result()
    )
    return SettingsEffectiveSnapshot(
        id=record.snapshot_id,
        resource=resource,
        effective_value=record.effective_payload,
        sources=tuple(
            ConfigSource.from_payload(item)
            for item in record.sources
            if isinstance(item, dict)
        ),
        overrides=tuple(
            ConfigSource.from_payload(item)
            for item in record.overrides_applied
            if isinstance(item, dict)
        ),
        environment=None if record.scope_key == "default" else record.scope_key,
        version_id=record.version_id,
        validation=validation,
        created_at=record.generated_at or record.created_at,
        metadata=record.metadata,
    )


def _version_number_from_sources(sources: tuple[ConfigSource, ...]) -> int | None:
    for source in sources:
        value = source.metadata.get("version_number")
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None


__all__ = ["snapshot_from_record", "snapshot_record_from_domain"]
