from __future__ import annotations

from datetime import datetime, timezone

from crxzipple.modules.settings.infrastructure.persistence.models import (
    SettingsActionAuditModel,
    SettingsEffectiveSnapshotModel,
    SettingsOverrideModel,
    SettingsResourceModel,
    SettingsResourceVersionModel,
    SettingsValidationResultModel,
)
from crxzipple.modules.settings.infrastructure.persistence.records import (
    SettingsActionAuditRecord,
    SettingsEffectiveSnapshotRecord,
    SettingsOverrideRecord,
    SettingsResourceRecord,
    SettingsResourceVersionRecord,
    SettingsValidationResultRecord,
)
from crxzipple.shared.time import coerce_optional_utc_datetime, coerce_utc_datetime


def _resource_model(record: SettingsResourceRecord) -> SettingsResourceModel:
    return SettingsResourceModel(
        resource_id=_required_text(record.resource_id, "resource id"),
        resource_kind=_required_text(record.resource_kind, "resource kind"),
        display_name=_optional_text(record.display_name),
        governance_scope=_required_text(record.governance_scope, "governance scope"),
        config_contract=dict(record.config_contract),
        contract_version=_optional_text(record.contract_version),
        storage_key=_required_text(record.storage_key, "storage key"),
        consumer_modules=list(record.consumer_modules),
        resolution_policy=dict(record.resolution_policy),
        supports_create=bool(record.supports_create),
        supports_update=bool(record.supports_update),
        supports_delete=bool(record.supports_delete),
        supports_enable=bool(record.supports_enable),
        supports_disable=bool(record.supports_disable),
        supports_import=bool(record.supports_import),
        supports_export=bool(record.supports_export),
        validation_policy=dict(record.validation_policy),
        dry_run_policy=dict(record.dry_run_policy),
        audit_required=bool(record.audit_required),
        secret_policy=dict(record.secret_policy),
        status=_required_text(record.status, "status"),
        latest_version_number=record.latest_version_number,
        published_version_id=_optional_text(record.published_version_id),
        published_version_number=record.published_version_number,
        degraded_reason=_optional_text(record.degraded_reason),
        metadata_=dict(record.metadata),
        created_at=_record_created_at(record),
        updated_at=_record_updated_at(record),
    )


def _apply_resource(
    model: SettingsResourceModel,
    record: SettingsResourceRecord,
) -> None:
    updated = _resource_model(record)
    model.resource_kind = updated.resource_kind
    model.display_name = updated.display_name
    model.governance_scope = updated.governance_scope
    model.config_contract = updated.config_contract
    model.contract_version = updated.contract_version
    model.storage_key = updated.storage_key
    model.consumer_modules = updated.consumer_modules
    model.resolution_policy = updated.resolution_policy
    model.supports_create = updated.supports_create
    model.supports_update = updated.supports_update
    model.supports_delete = updated.supports_delete
    model.supports_enable = updated.supports_enable
    model.supports_disable = updated.supports_disable
    model.supports_import = updated.supports_import
    model.supports_export = updated.supports_export
    model.validation_policy = updated.validation_policy
    model.dry_run_policy = updated.dry_run_policy
    model.audit_required = updated.audit_required
    model.secret_policy = updated.secret_policy
    model.status = updated.status
    model.latest_version_number = updated.latest_version_number
    model.published_version_id = updated.published_version_id
    model.published_version_number = updated.published_version_number
    model.degraded_reason = updated.degraded_reason
    model.metadata_ = updated.metadata_
    model.created_at = updated.created_at
    model.updated_at = updated.updated_at


def _resource_record(model: SettingsResourceModel) -> SettingsResourceRecord:
    return SettingsResourceRecord(
        resource_id=model.resource_id,
        resource_kind=model.resource_kind,
        display_name=model.display_name,
        governance_scope=model.governance_scope,
        config_contract=dict(model.config_contract),
        contract_version=model.contract_version,
        storage_key=model.storage_key,
        consumer_modules=tuple(model.consumer_modules),
        resolution_policy=dict(model.resolution_policy),
        supports_create=model.supports_create,
        supports_update=model.supports_update,
        supports_delete=model.supports_delete,
        supports_enable=model.supports_enable,
        supports_disable=model.supports_disable,
        supports_import=model.supports_import,
        supports_export=model.supports_export,
        validation_policy=dict(model.validation_policy),
        dry_run_policy=dict(model.dry_run_policy),
        audit_required=model.audit_required,
        secret_policy=dict(model.secret_policy),
        status=model.status,
        latest_version_number=model.latest_version_number,
        published_version_id=model.published_version_id,
        published_version_number=model.published_version_number,
        degraded_reason=model.degraded_reason,
        metadata=dict(model.metadata_),
        created_at=coerce_utc_datetime(model.created_at),
        updated_at=coerce_utc_datetime(model.updated_at),
    )


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


def _action_audit_record(model: SettingsActionAuditModel) -> SettingsActionAuditRecord:
    return SettingsActionAuditRecord(
        audit_id=model.audit_id,
        action_id=model.action_id,
        action_type=model.action_type,
        target_type=model.target_type,
        target_id=model.target_id,
        resource_id=model.resource_id,
        resource_kind=model.resource_kind,
        status=model.status,
        actor=model.actor,
        source=model.source,
        reason=model.reason,
        risk=model.risk,
        confirmation=model.confirmation,
        risk_acknowledged=model.risk_acknowledged,
        request_metadata=dict(model.request_metadata),
        result=dict(model.result) if model.result is not None else None,
        error=dict(model.error) if model.error is not None else None,
        redaction_policy=dict(model.redaction_policy),
        trace_context=dict(model.trace_context),
        created_at=coerce_utc_datetime(model.created_at),
        updated_at=coerce_utc_datetime(model.updated_at),
    )


def _with_create_timestamps(record: object) -> dict[str, datetime]:
    created_at = _record_created_at(record)
    updated_at = getattr(record, "updated_at", None)
    return {
        "created_at": created_at,
        "updated_at": coerce_utc_datetime(updated_at) if updated_at else created_at,
    }


def _version_timestamps(record: SettingsResourceVersionRecord) -> dict[str, datetime]:
    timestamps = _with_create_timestamps(record)
    if record.status == "published" and record.published_at is None:
        return {**timestamps, "published_at": timestamps["updated_at"]}
    return timestamps


def _snapshot_timestamps(
    record: SettingsEffectiveSnapshotRecord,
) -> dict[str, datetime]:
    created_at = _record_created_at(record)
    updated_at = getattr(record, "updated_at", None)
    generated_at = getattr(record, "generated_at", None)
    return {
        "created_at": created_at,
        "updated_at": coerce_utc_datetime(updated_at) if updated_at else created_at,
        "generated_at": coerce_utc_datetime(generated_at) if generated_at else created_at,
    }


def _record_created_at(record: object) -> datetime:
    created_at = getattr(record, "created_at", None)
    return _coerce_or_now(created_at)


def _record_updated_at(record: object) -> datetime:
    updated_at = getattr(record, "updated_at", None)
    if updated_at is not None:
        return coerce_utc_datetime(updated_at)
    return _record_created_at(record)


def _record_generated_at(record: object) -> datetime:
    generated_at = getattr(record, "generated_at", None)
    if generated_at is not None:
        return coerce_utc_datetime(generated_at)
    return _record_created_at(record)


def _coerce_or_now(value: datetime | None) -> datetime:
    return coerce_utc_datetime(value or datetime.now(timezone.utc))


def _required_text(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"settings {label} cannot be blank")
    return normalized


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
