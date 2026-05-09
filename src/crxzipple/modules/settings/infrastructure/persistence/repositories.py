from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from crxzipple.core.db import SessionFactory
from crxzipple.modules.settings.infrastructure.persistence.models import (
    SettingsActionAuditModel,
    SettingsEffectiveSnapshotModel,
    SettingsOverrideModel,
    SettingsResourceModel,
    SettingsResourceVersionModel,
    SettingsValidationResultModel,
)
from crxzipple.shared.time import coerce_optional_utc_datetime, coerce_utc_datetime


JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class SettingsResourceRecord:
    resource_id: str
    resource_kind: str
    governance_scope: str
    config_contract: JsonObject
    storage_key: str
    display_name: str | None = None
    contract_version: str | None = None
    consumer_modules: tuple[str, ...] = ()
    resolution_policy: JsonObject = field(default_factory=dict)
    supports_create: bool = True
    supports_update: bool = True
    supports_delete: bool = True
    supports_enable: bool = True
    supports_disable: bool = True
    supports_import: bool = True
    supports_export: bool = True
    validation_policy: JsonObject = field(default_factory=dict)
    dry_run_policy: JsonObject = field(default_factory=dict)
    audit_required: bool = True
    secret_policy: JsonObject = field(default_factory=dict)
    status: str = "active"
    latest_version_number: int | None = None
    published_version_id: str | None = None
    published_version_number: int | None = None
    degraded_reason: str | None = None
    metadata: JsonObject = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SettingsResourceVersionRecord:
    version_id: str
    resource_id: str
    resource_kind: str
    version_number: int
    payload: JsonObject
    status: str = "draft"
    source_kind: str = "manual"
    source_ref: str | None = None
    source_metadata: JsonObject = field(default_factory=dict)
    contract_version: str | None = None
    redaction_policy: JsonObject = field(default_factory=dict)
    validation_result_id: str | None = None
    created_by: str | None = None
    reason: str | None = None
    published_at: datetime | None = None
    metadata: JsonObject = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SettingsEffectiveSnapshotRecord:
    snapshot_id: str
    resource_id: str
    resource_kind: str
    effective_payload: JsonObject
    scope_key: str = "default"
    version_id: str | None = None
    version_number: int | None = None
    resolution_trace: tuple[JsonObject, ...] = ()
    sources: tuple[JsonObject, ...] = ()
    overrides_applied: tuple[JsonObject, ...] = ()
    status: str = "active"
    is_current: bool = True
    generated_at: datetime | None = None
    metadata: JsonObject = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SettingsOverrideRecord:
    override_id: str
    resource_id: str
    resource_kind: str
    override_kind: str
    scope_key: str
    override_payload: JsonObject
    priority: int = 100
    status: str = "active"
    source_kind: str = "manual"
    source_ref: str | None = None
    reason: str | None = None
    actor: str | None = None
    expires_at: datetime | None = None
    redaction_policy: JsonObject = field(default_factory=dict)
    metadata: JsonObject = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SettingsValidationResultRecord:
    validation_id: str
    resource_id: str
    resource_kind: str
    validator: str
    status: str
    valid: bool
    version_id: str | None = None
    audit_id: str | None = None
    issues: tuple[JsonObject, ...] = ()
    checked_payload_digest: str | None = None
    redaction_policy: JsonObject = field(default_factory=dict)
    metadata: JsonObject = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SettingsActionAuditRecord:
    audit_id: str
    action_type: str
    target_type: str
    target_id: str | None
    status: str
    reason: str
    actor: str | None = None
    action_id: str | None = None
    resource_id: str | None = None
    resource_kind: str | None = None
    source: str = "settings"
    risk: str = "normal"
    confirmation: bool = False
    risk_acknowledged: bool = False
    request_metadata: JsonObject = field(default_factory=dict)
    result: JsonObject | None = None
    error: JsonObject | None = None
    redaction_policy: JsonObject = field(default_factory=dict)
    trace_context: JsonObject = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SqlAlchemySettingsGovernanceRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def create_resource(self, record: SettingsResourceRecord) -> SettingsResourceRecord:
        stored = replace(record, **_with_create_timestamps(record))
        with self._session_factory() as session:
            session.add(_resource_model(stored))
            session.commit()
        return stored

    def update_resource(self, record: SettingsResourceRecord) -> SettingsResourceRecord:
        with self._session_factory() as session:
            model = session.get(
                SettingsResourceModel,
                _required_text(record.resource_id, "resource id"),
            )
            if model is None:
                raise LookupError(
                    f"Settings resource '{record.resource_id}' does not exist.",
                )
            stored = replace(
                record,
                created_at=record.created_at or coerce_utc_datetime(model.created_at),
                updated_at=_coerce_or_now(record.updated_at),
            )
            _apply_resource(model, stored)
            session.commit()
            return _resource_record(model)

    def get_resource(self, resource_id: str) -> SettingsResourceRecord | None:
        with self._session_factory() as session:
            model = session.get(
                SettingsResourceModel,
                _required_text(resource_id, "resource id"),
            )
            return _resource_record(model) if model is not None else None

    def list_resources(
        self,
        *,
        resource_kind: str | None = None,
        status: str | None = None,
    ) -> tuple[SettingsResourceRecord, ...]:
        with self._session_factory() as session:
            statement = select(SettingsResourceModel).order_by(
                SettingsResourceModel.resource_kind.asc(),
                SettingsResourceModel.resource_id.asc(),
            )
            if resource_kind is not None:
                statement = statement.where(
                    SettingsResourceModel.resource_kind
                    == _required_text(resource_kind, "resource kind"),
                )
            if status is not None:
                statement = statement.where(
                    SettingsResourceModel.status == _required_text(status, "status"),
                )
            return tuple(_resource_record(model) for model in session.scalars(statement))

    def create_version(
        self,
        record: SettingsResourceVersionRecord,
    ) -> SettingsResourceVersionRecord:
        stored = replace(record, **_version_timestamps(record))
        with self._session_factory() as session:
            session.add(_version_model(stored))
            resource = session.get(SettingsResourceModel, stored.resource_id)
            if resource is not None:
                latest = resource.latest_version_number
                if latest is None or stored.version_number > latest:
                    resource.latest_version_number = stored.version_number
                if stored.status == "published":
                    resource.published_version_id = stored.version_id
                    resource.published_version_number = stored.version_number
                resource.updated_at = _record_updated_at(stored)
            session.commit()
        return stored

    def get_version(self, version_id: str) -> SettingsResourceVersionRecord | None:
        with self._session_factory() as session:
            model = session.get(
                SettingsResourceVersionModel,
                _required_text(version_id, "version id"),
            )
            return _version_record(model) if model is not None else None

    def list_versions(self, resource_id: str) -> tuple[SettingsResourceVersionRecord, ...]:
        with self._session_factory() as session:
            models = session.scalars(
                select(SettingsResourceVersionModel)
                .where(
                    SettingsResourceVersionModel.resource_id
                    == _required_text(resource_id, "resource id"),
                )
                .order_by(
                    SettingsResourceVersionModel.version_number.desc(),
                    SettingsResourceVersionModel.created_at.desc(),
                ),
            ).all()
            return tuple(_version_record(model) for model in models)

    def get_latest_published_version(
        self,
        resource_id: str,
    ) -> SettingsResourceVersionRecord | None:
        with self._session_factory() as session:
            model = session.scalars(
                select(SettingsResourceVersionModel)
                .where(
                    SettingsResourceVersionModel.resource_id
                    == _required_text(resource_id, "resource id"),
                    SettingsResourceVersionModel.status == "published",
                )
                .order_by(
                    SettingsResourceVersionModel.published_at.desc().nullslast(),
                    SettingsResourceVersionModel.version_number.desc(),
                    SettingsResourceVersionModel.created_at.desc(),
                )
                .limit(1),
            ).first()
            return _version_record(model) if model is not None else None

    def record_effective_snapshot(
        self,
        record: SettingsEffectiveSnapshotRecord,
    ) -> SettingsEffectiveSnapshotRecord:
        stored = replace(record, **_snapshot_timestamps(record))
        with self._session_factory() as session:
            if stored.is_current:
                previous = session.scalars(
                    select(SettingsEffectiveSnapshotModel).where(
                        SettingsEffectiveSnapshotModel.resource_id == stored.resource_id,
                        SettingsEffectiveSnapshotModel.scope_key == stored.scope_key,
                        SettingsEffectiveSnapshotModel.is_current.is_(True),
                    ),
                ).all()
                now = _record_updated_at(stored)
                for snapshot in previous:
                    snapshot.is_current = False
                    snapshot.updated_at = now
            session.add(_snapshot_model(stored))
            session.commit()
        return stored

    def get_latest_effective_snapshot(
        self,
        resource_id: str,
        *,
        scope_key: str = "default",
    ) -> SettingsEffectiveSnapshotRecord | None:
        normalized_resource_id = _required_text(resource_id, "resource id")
        normalized_scope_key = _required_text(scope_key, "scope key")
        with self._session_factory() as session:
            model = session.scalars(
                select(SettingsEffectiveSnapshotModel)
                .where(
                    SettingsEffectiveSnapshotModel.resource_id == normalized_resource_id,
                    SettingsEffectiveSnapshotModel.scope_key == normalized_scope_key,
                    SettingsEffectiveSnapshotModel.is_current.is_(True),
                )
                .order_by(
                    SettingsEffectiveSnapshotModel.generated_at.desc(),
                    SettingsEffectiveSnapshotModel.snapshot_id.desc(),
                )
                .limit(1),
            ).first()
            if model is None:
                model = session.scalars(
                    select(SettingsEffectiveSnapshotModel)
                    .where(
                        SettingsEffectiveSnapshotModel.resource_id
                        == normalized_resource_id,
                        SettingsEffectiveSnapshotModel.scope_key == normalized_scope_key,
                    )
                    .order_by(
                        SettingsEffectiveSnapshotModel.generated_at.desc(),
                        SettingsEffectiveSnapshotModel.snapshot_id.desc(),
                    )
                    .limit(1),
                ).first()
            return _snapshot_record(model) if model is not None else None

    def list_effective_snapshots(
        self,
        resource_id: str,
        *,
        scope_key: str | None = None,
    ) -> tuple[SettingsEffectiveSnapshotRecord, ...]:
        with self._session_factory() as session:
            statement = (
                select(SettingsEffectiveSnapshotModel)
                .where(
                    SettingsEffectiveSnapshotModel.resource_id
                    == _required_text(resource_id, "resource id"),
                )
                .order_by(
                    SettingsEffectiveSnapshotModel.generated_at.desc(),
                    SettingsEffectiveSnapshotModel.snapshot_id.desc(),
                )
            )
            if scope_key is not None:
                statement = statement.where(
                    SettingsEffectiveSnapshotModel.scope_key
                    == _required_text(scope_key, "scope key"),
                )
            return tuple(_snapshot_record(model) for model in session.scalars(statement))

    def create_override(
        self,
        record: SettingsOverrideRecord,
    ) -> SettingsOverrideRecord:
        stored = replace(record, **_with_create_timestamps(record))
        with self._session_factory() as session:
            session.add(_override_model(stored))
            session.commit()
        return stored

    def list_overrides(
        self,
        *,
        resource_id: str | None = None,
        scope_key: str | None = None,
        status: str | None = None,
    ) -> tuple[SettingsOverrideRecord, ...]:
        with self._session_factory() as session:
            statement = select(SettingsOverrideModel).order_by(
                SettingsOverrideModel.priority.desc(),
                SettingsOverrideModel.created_at.desc(),
                SettingsOverrideModel.override_id.asc(),
            )
            if resource_id is not None:
                statement = statement.where(
                    SettingsOverrideModel.resource_id
                    == _required_text(resource_id, "resource id"),
                )
            if scope_key is not None:
                statement = statement.where(
                    SettingsOverrideModel.scope_key
                    == _required_text(scope_key, "scope key"),
                )
            if status is not None:
                statement = statement.where(
                    SettingsOverrideModel.status == _required_text(status, "status"),
                )
            return tuple(_override_record(model) for model in session.scalars(statement))

    def record_validation_result(
        self,
        record: SettingsValidationResultRecord,
    ) -> SettingsValidationResultRecord:
        stored = replace(record, created_at=_record_created_at(record))
        with self._session_factory() as session:
            session.add(_validation_result_model(stored))
            session.commit()
        return stored

    def list_validation_results(
        self,
        *,
        resource_id: str | None = None,
        version_id: str | None = None,
    ) -> tuple[SettingsValidationResultRecord, ...]:
        with self._session_factory() as session:
            statement = select(SettingsValidationResultModel).order_by(
                SettingsValidationResultModel.created_at.desc(),
                SettingsValidationResultModel.validation_id.asc(),
            )
            if resource_id is not None:
                statement = statement.where(
                    SettingsValidationResultModel.resource_id
                    == _required_text(resource_id, "resource id"),
                )
            if version_id is not None:
                statement = statement.where(
                    SettingsValidationResultModel.version_id
                    == _required_text(version_id, "version id"),
                )
            return tuple(
                _validation_result_record(model) for model in session.scalars(statement)
            )


class SqlAlchemySettingsActionAuditRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def record_attempt(
        self,
        *,
        action_type: str,
        target_type: str,
        target_id: str | None,
        reason: str,
        actor: str | None = None,
        action_id: str | None = None,
        resource_id: str | None = None,
        resource_kind: str | None = None,
        source: str = "settings",
        risk: str = "normal",
        confirmation: bool = False,
        risk_acknowledged: bool = False,
        request_metadata: JsonObject | None = None,
        redaction_policy: JsonObject | None = None,
        trace_context: JsonObject | None = None,
        created_at: datetime | None = None,
    ) -> SettingsActionAuditRecord:
        now = _coerce_or_now(created_at)
        model = SettingsActionAuditModel(
            audit_id=f"settingsact_{uuid4().hex}",
            action_id=_optional_text(action_id),
            action_type=_required_text(action_type, "action type"),
            target_type=_required_text(target_type, "target type"),
            target_id=_optional_text(target_id),
            resource_id=_optional_text(resource_id) or _optional_text(target_id),
            resource_kind=_optional_text(resource_kind),
            status="attempted",
            actor=_optional_text(actor),
            source=_required_text(source, "source"),
            reason=_required_text(reason, "reason"),
            risk=_required_text(risk, "risk"),
            confirmation=bool(confirmation),
            risk_acknowledged=bool(risk_acknowledged),
            request_metadata=dict(request_metadata or {}),
            result=None,
            error=None,
            redaction_policy=dict(redaction_policy or {}),
            trace_context=dict(trace_context or {}),
            created_at=now,
            updated_at=now,
        )
        with self._session_factory() as session:
            session.add(model)
            session.commit()
            return _action_audit_record(model)

    def mark_succeeded(
        self,
        audit_id: str,
        *,
        result: JsonObject | None = None,
        updated_at: datetime | None = None,
    ) -> SettingsActionAuditRecord:
        return self._mark_terminal(
            audit_id,
            status="succeeded",
            result=dict(result) if result is not None else None,
            error=None,
            updated_at=updated_at,
        )

    def mark_failed(
        self,
        audit_id: str,
        *,
        error: JsonObject,
        updated_at: datetime | None = None,
    ) -> SettingsActionAuditRecord:
        return self._mark_terminal(
            audit_id,
            status="failed",
            result=None,
            error=dict(error),
            updated_at=updated_at,
        )

    def list_recent(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[SettingsActionAuditRecord, ...]:
        safe_limit = min(max(int(limit), 1), 200)
        safe_offset = max(int(offset), 0)
        with self._session_factory() as session:
            models = session.scalars(
                select(SettingsActionAuditModel)
                .order_by(
                    SettingsActionAuditModel.created_at.desc(),
                    SettingsActionAuditModel.audit_id.desc(),
                )
                .limit(safe_limit)
                .offset(safe_offset),
            ).all()
            return tuple(_action_audit_record(model) for model in models)

    def _mark_terminal(
        self,
        audit_id: str,
        *,
        status: str,
        result: JsonObject | None,
        error: JsonObject | None,
        updated_at: datetime | None,
    ) -> SettingsActionAuditRecord:
        with self._session_factory() as session:
            model = session.get(
                SettingsActionAuditModel,
                _required_text(audit_id, "audit id"),
            )
            if model is None:
                raise LookupError(f"Settings action audit '{audit_id}' does not exist.")
            model.status = status
            model.result = result
            model.error = error
            model.updated_at = _coerce_or_now(updated_at)
            session.commit()
            return _action_audit_record(model)


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
