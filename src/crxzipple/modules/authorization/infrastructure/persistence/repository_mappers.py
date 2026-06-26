from __future__ import annotations

from datetime import datetime

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


def policy_model(
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


def policy_entity(model: AuthorizationPolicyModel) -> AuthorizationPolicy:
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


def temporary_grant_model(
    grant: TemporaryAuthorizationGrant,
) -> TemporaryAuthorizationGrantModel:
    return TemporaryAuthorizationGrantModel(
        id=grant.id,
        scope=grant.scope.value,
        run_id=grant.run_id,
        session_key=grant.session_key,
        agent_id=grant.agent_id,
        approval_request_id=grant.approval_request_id,
        effect_ids_payload=list(grant.effect_ids),
        tool_ids_payload=list(grant.tool_ids),
        created_at=grant.created_at,
    )


def temporary_grant_entity(
    model: TemporaryAuthorizationGrantModel,
) -> TemporaryAuthorizationGrant:
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


def audit_model(record: AuthorizationAuditRecord) -> AuthorizationAuditModel:
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


def audit_entity(model: AuthorizationAuditModel) -> AuthorizationAuditRecord:
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


__all__ = [
    "audit_entity",
    "audit_model",
    "policy_entity",
    "policy_model",
    "temporary_grant_entity",
    "temporary_grant_model",
]
