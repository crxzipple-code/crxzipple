from __future__ import annotations

from crxzipple.modules.settings.infrastructure.persistence.models import (
    SettingsResourceModel,
)
from crxzipple.modules.settings.infrastructure.persistence.records import (
    SettingsResourceRecord,
)
from crxzipple.modules.settings.infrastructure.persistence.repository_values import (
    _optional_text,
    _record_created_at,
    _record_updated_at,
    _required_text,
)
from crxzipple.shared.time import coerce_utc_datetime


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
