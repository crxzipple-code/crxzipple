from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock

from sqlalchemy import select

from crxzipple.core.db import SessionFactory
from crxzipple.modules.authorization.domain import (
    AuthorizationAuditRecord,
    AuthorizationPolicy,
    TemporaryAuthorizationGrant,
)
from crxzipple.modules.authorization.infrastructure.persistence.models import (
    AuthorizationAuditModel,
    AuthorizationPolicyModel,
    TemporaryAuthorizationGrantModel,
)
from crxzipple.modules.authorization.infrastructure.persistence.repository_mappers import (
    audit_entity,
    audit_model,
    policy_entity,
    policy_model,
    temporary_grant_entity,
    temporary_grant_model,
)


@dataclass(slots=True)
class SqlAlchemyAuthorizationPolicyRepository:
    session_factory: SessionFactory
    bootstrap_policies: tuple[AuthorizationPolicy, ...] = ()
    _bootstrap_imported: bool = field(default=False, init=False)
    _bootstrap_lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def get(self, policy_id: str) -> AuthorizationPolicy | None:
        self._ensure_bootstrap_imported()
        with self.session_factory() as session:
            model = session.get(AuthorizationPolicyModel, policy_id)
        return policy_entity(model) if model is not None else None

    def list(self) -> list[AuthorizationPolicy]:
        self._ensure_bootstrap_imported()
        with self.session_factory() as session:
            models = session.scalars(
                select(AuthorizationPolicyModel).order_by(
                    AuthorizationPolicyModel.priority.desc(),
                    AuthorizationPolicyModel.policy_id.asc(),
                ),
            ).all()
        return [policy_entity(model) for model in models]

    def upsert(self, policy: AuthorizationPolicy) -> None:
        self._ensure_bootstrap_imported()
        self._upsert(policy)

    def delete(self, policy_id: str) -> bool:
        self._ensure_bootstrap_imported()
        with self.session_factory() as session:
            model = session.get(AuthorizationPolicyModel, policy_id)
            if model is None:
                return False
            session.delete(model)
            session.commit()
            return True

    def _ensure_bootstrap_imported(self) -> None:
        if self._bootstrap_imported:
            return
        with self._bootstrap_lock:
            if self._bootstrap_imported:
                return
            for policy in self.bootstrap_policies:
                self._upsert(policy, insert_only=True)
            self._bootstrap_imported = True

    def _upsert(
        self,
        policy: AuthorizationPolicy,
        *,
        insert_only: bool = False,
    ) -> None:
        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            existing = session.get(AuthorizationPolicyModel, policy.id)
            if insert_only and existing is not None:
                return
            created_at = existing.created_at if existing is not None else now
            session.merge(policy_model(policy, created_at=created_at, updated_at=now))
            session.commit()


class SqlAlchemyTemporaryAuthorizationGrantRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def add(self, grant: TemporaryAuthorizationGrant) -> None:
        with self.session_factory() as session:
            session.merge(temporary_grant_model(grant))
            session.commit()

    def list_for_run(self, run_id: str) -> list[TemporaryAuthorizationGrant]:
        with self.session_factory() as session:
            models = session.scalars(
                select(TemporaryAuthorizationGrantModel)
                .where(TemporaryAuthorizationGrantModel.run_id == run_id)
                .order_by(TemporaryAuthorizationGrantModel.created_at.asc()),
            ).all()
        return [temporary_grant_entity(model) for model in models]

    def list_for_session(self, session_key: str) -> list[TemporaryAuthorizationGrant]:
        with self.session_factory() as session:
            models = session.scalars(
                select(TemporaryAuthorizationGrantModel)
                .where(TemporaryAuthorizationGrantModel.session_key == session_key)
                .order_by(TemporaryAuthorizationGrantModel.created_at.asc()),
            ).all()
        return [temporary_grant_entity(model) for model in models]


@dataclass(slots=True)
class SqlAlchemyAuthorizationAuditRepository:
    session_factory: SessionFactory

    def add(self, record: AuthorizationAuditRecord) -> None:
        with self.session_factory() as session:
            session.add(audit_model(record))
            session.commit()

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        action: str | None = None,
        target_policy_id: str | None = None,
    ) -> list[AuthorizationAuditRecord]:
        normalized_limit = max(1, min(int(limit), 200))
        normalized_offset = max(0, int(offset))
        statement = select(AuthorizationAuditModel)
        if action is not None and action.strip():
            statement = statement.where(AuthorizationAuditModel.action == action.strip())
        if target_policy_id is not None and target_policy_id.strip():
            statement = statement.where(
                AuthorizationAuditModel.target_policy_id == target_policy_id.strip(),
            )
        statement = (
            statement.order_by(AuthorizationAuditModel.created_at.desc())
            .offset(normalized_offset)
            .limit(normalized_limit)
        )
        with self.session_factory() as session:
            models = session.scalars(statement).all()
        return [audit_entity(model) for model in models]
