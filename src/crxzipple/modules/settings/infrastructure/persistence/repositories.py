from __future__ import annotations

from dataclasses import replace
from datetime import datetime
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
from crxzipple.modules.settings.infrastructure.persistence.records import (
    JsonObject,
    SettingsActionAuditRecord,
    SettingsEffectiveSnapshotRecord,
    SettingsOverrideRecord,
    SettingsResourceRecord,
    SettingsResourceVersionRecord,
    SettingsValidationResultRecord,
)
from crxzipple.modules.settings.infrastructure.persistence.repository_mappers import (
    _action_audit_record,
    _apply_resource,
    _coerce_or_now,
    _optional_text,
    _override_model,
    _override_record,
    _record_created_at,
    _record_updated_at,
    _required_text,
    _resource_model,
    _resource_record,
    _snapshot_model,
    _snapshot_record,
    _snapshot_timestamps,
    _validation_result_model,
    _validation_result_record,
    _version_model,
    _version_record,
    _version_timestamps,
    _with_create_timestamps,
)
from crxzipple.shared.time import coerce_utc_datetime


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
