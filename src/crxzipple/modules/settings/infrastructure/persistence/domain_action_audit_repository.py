from __future__ import annotations

from typing import Any

from sqlalchemy import select

from crxzipple.core.db import SessionFactory
from crxzipple.modules.settings.domain.entities import SettingsActionAudit
from crxzipple.modules.settings.infrastructure.persistence.domain_repository_mappers import (
    _apply_audit,
    _audit_from_record,
    _audit_model_from_domain,
    _uuid_hex,
)
from crxzipple.modules.settings.infrastructure.persistence.models import (
    SettingsActionAuditModel,
)
from crxzipple.modules.settings.infrastructure.persistence.repository_mappers import (
    _action_audit_record,
    _required_text,
)


class SqlAlchemySettingsActionAuditDomainRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self._live_audits: dict[str, SettingsActionAudit] = {}

    def record_attempt(
        self,
        *,
        action_type: str,
        target_type: str,
        target_id: str | None,
        reason: str,
        actor: str | None = None,
        risk: str | None = None,
        request_metadata: dict[str, Any] | None = None,
    ) -> SettingsActionAudit:
        audit = SettingsActionAudit(
            id=f"settings_audit_{_uuid_hex()}",
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
            reason=reason,
            actor=actor,
            risk=risk,
            request_metadata=dict(request_metadata or {}),
        )
        with self._session_factory() as session:
            session.add(_audit_model_from_domain(audit))
            session.commit()
        self._live_audits[audit.id] = audit
        return audit

    def mark_succeeded(
        self,
        audit_id: str,
        *,
        result: dict[str, Any] | None = None,
    ) -> SettingsActionAudit:
        audit = self._require(audit_id)
        audit.mark_succeeded(result=result)
        self._save(audit)
        return audit

    def mark_failed(
        self,
        audit_id: str,
        *,
        error: dict[str, Any],
    ) -> SettingsActionAudit:
        audit = self._require(audit_id)
        audit.mark_failed(error=error)
        self._save(audit)
        return audit

    def get(self, audit_id: str) -> SettingsActionAudit | None:
        live = self._live_audits.get(audit_id)
        if live is not None:
            return live
        with self._session_factory() as session:
            model = session.get(
                SettingsActionAuditModel,
                _required_text(audit_id, "audit id"),
            )
            if model is None:
                return None
            return _audit_from_record(_action_audit_record(model))

    def list(self) -> tuple[SettingsActionAudit, ...]:
        with self._session_factory() as session:
            models = session.scalars(
                select(SettingsActionAuditModel).order_by(
                    SettingsActionAuditModel.created_at.asc(),
                    SettingsActionAuditModel.audit_id.asc(),
                ),
            ).all()
            return tuple(_audit_from_record(_action_audit_record(model)) for model in models)

    def _require(self, audit_id: str) -> SettingsActionAudit:
        audit = self.get(audit_id)
        if audit is None:
            raise LookupError(f"Settings action audit '{audit_id}' does not exist.")
        return audit

    def _save(self, audit: SettingsActionAudit) -> None:
        with self._session_factory() as session:
            model = session.get(SettingsActionAuditModel, audit.id)
            stored = _audit_model_from_domain(audit)
            if model is None:
                session.add(stored)
            else:
                _apply_audit(model, stored)
            session.commit()
        self._live_audits[audit.id] = audit
