from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import select

from crxzipple.core.db import SessionFactory
from crxzipple.modules.settings.infrastructure.persistence.models import (
    SettingsActionAuditModel,
)
from crxzipple.modules.settings.infrastructure.persistence.records import (
    JsonObject,
    SettingsActionAuditRecord,
)
from crxzipple.modules.settings.infrastructure.persistence.repository_action_audit_mappers import (
    _action_audit_record,
)
from crxzipple.modules.settings.infrastructure.persistence.repository_values import (
    _coerce_or_now,
    _optional_text,
    _required_text,
)
from crxzipple.modules.settings.infrastructure.persistence.redaction import (
    redacted_json_object,
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
            request_metadata=redacted_json_object(request_metadata) or {},
            result=None,
            error=None,
            redaction_policy=dict(redaction_policy or {}),
            trace_context=redacted_json_object(trace_context) or {},
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
            result=redacted_json_object(result),
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
            error=redacted_json_object(error),
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
