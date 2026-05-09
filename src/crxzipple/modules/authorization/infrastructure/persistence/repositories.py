from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock

from sqlalchemy import select

from crxzipple.core.db import SessionFactory
from crxzipple.modules.authorization.domain import (
    AuthorizationAuditRecord,
    AuthorizationEffect,
    AuthorizationGrantScope,
    AuthorizationObligation,
    AuthorizationPolicy,
    TemporaryAuthorizationGrant,
)
from crxzipple.modules.authorization.infrastructure.persistence.models import (
    AuthorizationAuditModel,
    AuthorizationPolicyModel,
    TemporaryAuthorizationGrantModel,
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
        return self._to_entity(model) if model is not None else None

    def list(self) -> list[AuthorizationPolicy]:
        self._ensure_bootstrap_imported()
        with self.session_factory() as session:
            models = session.scalars(
                select(AuthorizationPolicyModel).order_by(
                    AuthorizationPolicyModel.priority.desc(),
                    AuthorizationPolicyModel.policy_id.asc(),
                ),
            ).all()
        return [self._to_entity(model) for model in models]

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
            session.merge(_policy_model(policy, created_at=created_at, updated_at=now))
            session.commit()

    @staticmethod
    def _to_entity(model: AuthorizationPolicyModel) -> AuthorizationPolicy:
        return AuthorizationPolicy(
            id=model.policy_id,
            description=model.description,
            effect=AuthorizationEffect(model.effect),
            actions=_string_tuple(model.actions_payload),
            subject_type=model.subject_type,
            subject_id=model.subject_id,
            subject_match=dict(model.subject_match_payload or {}),
            resource_kind=model.resource_kind,
            resource_id=model.resource_id,
            resource_match=dict(model.resource_match_payload or {}),
            context_match=dict(model.context_match_payload or {}),
            condition=(
                dict(model.condition_payload)
                if isinstance(model.condition_payload, dict)
                else None
            ),
            obligations=_obligations_from_payload(model.obligations_payload),
            priority=model.priority,
            enabled=model.enabled,
            source_kind=model.source_kind,
        )


class SqlAlchemyTemporaryAuthorizationGrantRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def add(self, grant: TemporaryAuthorizationGrant) -> None:
        with self.session_factory() as session:
            session.merge(
                TemporaryAuthorizationGrantModel(
                    id=grant.id,
                    scope=grant.scope.value,
                    run_id=grant.run_id,
                    session_key=grant.session_key,
                    agent_id=grant.agent_id,
                    approval_request_id=grant.approval_request_id,
                    effect_ids_payload=list(grant.effect_ids),
                    tool_ids_payload=list(grant.tool_ids),
                    created_at=grant.created_at,
                ),
            )
            session.commit()

    def list_for_run(self, run_id: str) -> list[TemporaryAuthorizationGrant]:
        with self.session_factory() as session:
            models = session.scalars(
                select(TemporaryAuthorizationGrantModel)
                .where(TemporaryAuthorizationGrantModel.run_id == run_id)
                .order_by(TemporaryAuthorizationGrantModel.created_at.asc()),
            ).all()
        return [self._to_entity(model) for model in models]

    def list_for_session(self, session_key: str) -> list[TemporaryAuthorizationGrant]:
        with self.session_factory() as session:
            models = session.scalars(
                select(TemporaryAuthorizationGrantModel)
                .where(TemporaryAuthorizationGrantModel.session_key == session_key)
                .order_by(TemporaryAuthorizationGrantModel.created_at.asc()),
            ).all()
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_entity(model: TemporaryAuthorizationGrantModel) -> TemporaryAuthorizationGrant:
        return TemporaryAuthorizationGrant(
            id=model.id,
            scope=AuthorizationGrantScope(model.scope),
            run_id=model.run_id,
            session_key=model.session_key,
            agent_id=model.agent_id,
            approval_request_id=model.approval_request_id,
            effect_ids=tuple(model.effect_ids_payload),
            tool_ids=tuple(model.tool_ids_payload),
            created_at=model.created_at,
        )


@dataclass(slots=True)
class SqlAlchemyAuthorizationAuditRepository:
    session_factory: SessionFactory

    def add(self, record: AuthorizationAuditRecord) -> None:
        with self.session_factory() as session:
            session.add(_audit_model(record))
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
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_entity(model: AuthorizationAuditModel) -> AuthorizationAuditRecord:
        return AuthorizationAuditRecord(
            id=model.audit_id,
            action=model.action,
            status=model.status,
            actor_type=model.actor_type,
            actor_id=model.actor_id,
            target_policy_id=model.target_policy_id,
            reason=model.reason,
            before_payload=dict(model.before_payload or {}),
            after_payload=dict(model.after_payload or {}),
            decision_payload=dict(model.decision_payload or {}),
            metadata=dict(model.metadata_payload or {}),
            created_at=model.created_at,
        )


def _policy_model(
    policy: AuthorizationPolicy,
    *,
    created_at: datetime,
    updated_at: datetime,
) -> AuthorizationPolicyModel:
    return AuthorizationPolicyModel(
        policy_id=policy.id,
        description=policy.description,
        effect=policy.effect.value,
        actions_payload=list(policy.actions),
        subject_type=policy.subject_type,
        subject_id=policy.subject_id,
        subject_match_payload=dict(policy.subject_match),
        resource_kind=policy.resource_kind,
        resource_id=policy.resource_id,
        resource_match_payload=dict(policy.resource_match),
        context_match_payload=dict(policy.context_match),
        condition_payload=(
            dict(policy.condition)
            if isinstance(policy.condition, dict)
            else None
        ),
        obligations_payload=[
            (
                {"name": obligation.name, "params": dict(obligation.params)}
                if obligation.params
                else obligation.name
            )
            for obligation in policy.obligations
        ],
        priority=policy.priority,
        enabled=policy.enabled,
        source_kind=policy.source_kind,
        created_at=created_at,
        updated_at=updated_at,
    )


def _audit_model(record: AuthorizationAuditRecord) -> AuthorizationAuditModel:
    return AuthorizationAuditModel(
        audit_id=record.id,
        action=record.action,
        status=record.status,
        actor_type=record.actor_type,
        actor_id=record.actor_id,
        target_policy_id=record.target_policy_id,
        reason=record.reason,
        before_payload=dict(record.before_payload),
        after_payload=dict(record.after_payload),
        decision_payload=dict(record.decision_payload),
        metadata_payload=dict(record.metadata),
        created_at=record.created_at,
    )


def _obligations_from_payload(raw: object) -> tuple[AuthorizationObligation, ...]:
    if not isinstance(raw, list):
        return ()
    obligations: list[AuthorizationObligation] = []
    for item in raw:
        if isinstance(item, str):
            name = item.strip()
            if name:
                obligations.append(AuthorizationObligation(name=name))
            continue
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            params = item.get("params")
            obligations.append(
                AuthorizationObligation(
                    name=name,
                    params=dict(params) if isinstance(params, dict) else {},
                ),
            )
    return tuple(obligations)


def _string_tuple(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, (list, tuple)):
        return ()
    return tuple(
        dict.fromkeys(
            str(item).strip()
            for item in raw
            if str(item).strip()
        ),
    )
