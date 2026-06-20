from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from crxzipple.modules.authorization.domain import (
    AuthorizationAuditRecord,
    AuthorizationAuditRepository,
    AuthorizationContext,
    AuthorizationDecision,
    AuthorizationDecisionCode,
    AuthorizationDeniedError,
    AuthorizationEffect,
    AuthorizationGrantScope,
    AuthorizationPolicy,
    AuthorizationPolicyNotFoundError,
    AuthorizationPolicyRepository,
    AuthorizationRequest,
    TemporaryAuthorizationGrant,
    TemporaryAuthorizationGrantRepository,
    ToolExecutionAuthorizationRequest,
)


class AuthorizationEvaluator:
    def evaluate(
        self,
        request: AuthorizationRequest,
        policies: list[AuthorizationPolicy],
    ) -> AuthorizationDecision:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class GrantedAuthorizationPayload:
    tool_ids: tuple[str, ...] = ()
    effect_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AuthorizationImpactPreview:
    before: AuthorizationDecision
    after: AuthorizationDecision
    changed: bool
    added_policy_ids: tuple[str, ...] = ()
    updated_policy_ids: tuple[str, ...] = ()
    removed_policy_ids: tuple[str, ...] = ()


@dataclass(slots=True)
class AuthorizationApplicationService:
    policy_repository: AuthorizationPolicyRepository
    evaluator: AuthorizationEvaluator
    temporary_grant_repository_factory: (
        Callable[[], TemporaryAuthorizationGrantRepository] | None
    ) = None
    audit_repository: AuthorizationAuditRepository | None = None
    enabled: bool = False
    _policy_snapshot_cache: tuple[AuthorizationPolicy, ...] | None = field(
        default=None,
        init=False,
        repr=False,
    )

    def is_enabled(self) -> bool:
        return self.enabled

    def list_policies(self) -> list[AuthorizationPolicy]:
        return list(self._policy_snapshot())

    def check(self, request: AuthorizationRequest) -> AuthorizationDecision:
        if not self.enabled:
            return AuthorizationDecision(
                allowed=True,
                reason="authorization disabled",
                code=AuthorizationDecisionCode.AUTHORIZATION_DISABLED,
            )
        return self.evaluator.evaluate(request, list(self._policy_snapshot()))

    def authorize(self, request: AuthorizationRequest) -> AuthorizationDecision:
        decision = self.check(request)
        if not decision.allowed:
            raise AuthorizationDeniedError(decision.reason)
        return decision

    def check_tool_execution(
        self,
        request: ToolExecutionAuthorizationRequest,
    ) -> AuthorizationDecision:
        context_attrs = dict(request.context.attrs)
        temporary_authorization = self._temporary_granted_authorization(context_attrs)
        granted_tool_ids = tuple(
            tool_id.strip()
            for tool_id in (*request.granted_tool_ids, *temporary_authorization.tool_ids)
            if tool_id is not None and tool_id.strip()
        )
        granted_effect_ids = tuple(
            effect_id.strip()
            for effect_id in (
                *request.granted_effect_ids,
                *temporary_authorization.effect_ids,
            )
            if effect_id is not None and effect_id.strip()
        )
        base_context = AuthorizationContext(
            attrs={
                **context_attrs,
                "granted_tool_ids": list(granted_tool_ids),
                "granted_effect_ids": list(granted_effect_ids),
            },
        )

        tool_access_decision = self._evaluate_for_tool_execution(
            AuthorizationRequest(
                subject=request.subject,
                action="tool.authorize",
                resource=request.resource,
                context=base_context,
            ),
        )
        if tool_access_decision.code is AuthorizationDecisionCode.POLICY_DENIED:
            return tool_access_decision

        tool_run_decision = self._evaluate_for_tool_execution(
            AuthorizationRequest(
                subject=request.subject,
                action="tool.run",
                resource=request.resource,
                context=base_context,
            ),
        )
        if tool_run_decision.code is AuthorizationDecisionCode.POLICY_DENIED:
            return tool_run_decision

        required_effect_ids = tuple(
            effect_id.strip()
            for effect_id in request.required_effect_ids
            if effect_id is not None and effect_id.strip()
        )
        matched_policy_ids: list[str] = list(tool_access_decision.matched_policy_ids)
        obligations = list(tool_access_decision.obligations)
        matched_policy_ids.extend(tool_run_decision.matched_policy_ids)
        obligations.extend(tool_run_decision.obligations)
        allowed_effect_ids: set[str] = set()
        for effect_id in required_effect_ids:
            effect_decision = self._evaluate_for_tool_execution(
                AuthorizationRequest(
                    subject=request.subject,
                    action="tool.effect.authorize",
                    resource=request.resource,
                    context=AuthorizationContext(
                        attrs={
                            **base_context.attrs,
                            "requested_effect_id": effect_id,
                        },
                    ),
                ),
            )
            if effect_decision.code is AuthorizationDecisionCode.POLICY_DENIED:
                return AuthorizationDecision(
                    allowed=False,
                    reason=effect_decision.reason,
                    code=AuthorizationDecisionCode.POLICY_DENIED,
                    matched_policy_ids=effect_decision.matched_policy_ids,
                    obligations=effect_decision.obligations,
                    details={
                        **effect_decision.details,
                        "requested_effect_id": effect_id,
                    },
                )
            if effect_decision.allowed:
                allowed_effect_ids.add(effect_id)
                matched_policy_ids.extend(effect_decision.matched_policy_ids)
                obligations.extend(effect_decision.obligations)

        missing_effect_ids = [
            effect_id
            for effect_id in required_effect_ids
            if effect_id not in granted_effect_ids and effect_id not in allowed_effect_ids
        ]
        if missing_effect_ids:
            resource_id = request.resource.id or "this tool"
            return AuthorizationDecision(
                allowed=False,
                reason=(
                    f"Approval is required to execute '{resource_id}' with effect(s): "
                    + ", ".join(missing_effect_ids)
                    + "."
                ),
                code=AuthorizationDecisionCode.APPROVAL_REQUIRED,
                matched_policy_ids=tuple(dict.fromkeys(matched_policy_ids)),
                obligations=tuple(obligations),
                details={"missing_effect_ids": missing_effect_ids},
            )

        if request.resource.id is not None and request.resource.id in granted_tool_ids:
            return AuthorizationDecision(
                allowed=True,
                reason=(
                    "Tool execution allowed because temporary authorization was "
                    f"granted for '{request.resource.id}'."
                ),
                code=AuthorizationDecisionCode.ALLOW,
                matched_policy_ids=tuple(dict.fromkeys(matched_policy_ids)),
                obligations=tuple(obligations),
                details={
                    "granted_tool_ids": list(granted_tool_ids),
                    "granted_effect_ids": list(granted_effect_ids),
                },
            )
        if tool_access_decision.allowed:
            return AuthorizationDecision(
                allowed=True,
                reason=tool_access_decision.reason,
                code=AuthorizationDecisionCode.ALLOW,
                matched_policy_ids=tuple(dict.fromkeys(matched_policy_ids)),
                obligations=tuple(obligations),
                details={"granted_effect_ids": list(granted_effect_ids)},
            )

        return AuthorizationDecision(
            allowed=True,
            reason=(
                f"Tool execution allowed because required access is satisfied for "
                f"'{request.resource.id or 'tool'}'."
            ),
            code=AuthorizationDecisionCode.ALLOW,
            matched_policy_ids=tuple(dict.fromkeys(matched_policy_ids)),
            obligations=tuple(obligations),
        )

    def grant_run_authorization(
        self,
        *,
        run_id: str,
        agent_id: str | None,
        approval_request_id: str | None,
        effect_ids: tuple[str, ...],
        tool_ids: tuple[str, ...],
    ) -> TemporaryAuthorizationGrant:
        normalized_run_id = run_id.strip()
        if not normalized_run_id:
            raise ValueError("run_id cannot be empty.")
        grant = TemporaryAuthorizationGrant(
            id=_run_grant_id(normalized_run_id, approval_request_id),
            scope=AuthorizationGrantScope.RUN,
            run_id=normalized_run_id,
            agent_id=(agent_id or "").strip() or None,
            approval_request_id=(approval_request_id or "").strip() or None,
            effect_ids=_normalize_values(effect_ids),
            tool_ids=_normalize_values(tool_ids),
            created_at=datetime.now(timezone.utc),
        )
        self._store_temporary_grant(grant)
        self._record_audit(
            action="grant.run.create",
            status="succeeded",
            metadata={"grant": _grant_payload(grant)},
        )
        return grant

    def grant_session_authorization(
        self,
        *,
        session_key: str,
        agent_id: str | None,
        approval_request_id: str | None,
        effect_ids: tuple[str, ...],
        tool_ids: tuple[str, ...],
    ) -> TemporaryAuthorizationGrant:
        normalized_session_key = session_key.strip()
        if not normalized_session_key:
            raise ValueError("session_key cannot be empty.")
        grant = TemporaryAuthorizationGrant(
            id=_session_grant_id(normalized_session_key, approval_request_id),
            scope=AuthorizationGrantScope.SESSION,
            session_key=normalized_session_key,
            agent_id=(agent_id or "").strip() or None,
            approval_request_id=(approval_request_id or "").strip() or None,
            effect_ids=_normalize_values(effect_ids),
            tool_ids=_normalize_values(tool_ids),
            created_at=datetime.now(timezone.utc),
        )
        self._store_temporary_grant(grant)
        self._record_audit(
            action="grant.session.create",
            status="succeeded",
            metadata={"grant": _grant_payload(grant)},
        )
        return grant

    def _evaluate_for_tool_execution(
        self,
        request: AuthorizationRequest,
    ) -> AuthorizationDecision:
        if not self.enabled:
            return AuthorizationDecision(
                allowed=False,
                reason="authorization disabled for policy matching",
                code=AuthorizationDecisionCode.NO_MATCH,
            )
        return self.evaluator.evaluate(request, list(self._policy_snapshot()))

    def _policy_snapshot(self) -> tuple[AuthorizationPolicy, ...]:
        if self._policy_snapshot_cache is None:
            self._policy_snapshot_cache = tuple(self.policy_repository.list())
        return self._policy_snapshot_cache

    def _invalidate_policy_snapshot(self) -> None:
        self._policy_snapshot_cache = None

    def _store_temporary_grant(
        self,
        grant: TemporaryAuthorizationGrant,
    ) -> None:
        if self.temporary_grant_repository_factory is None:
            return
        repository = self.temporary_grant_repository_factory()
        repository.add(grant)

    def _temporary_granted_authorization(
        self,
        context_attrs: dict[str, object],
    ) -> GrantedAuthorizationPayload:
        if self.temporary_grant_repository_factory is None:
            return GrantedAuthorizationPayload()
        repository = self.temporary_grant_repository_factory()
        run_id = str(context_attrs.get("run_id", "")).strip()
        session_key = str(context_attrs.get("session_key", "")).strip()
        tool_ids: set[str] = set()
        effect_ids: set[str] = set()
        if run_id:
            for grant in repository.list_for_run(run_id):
                tool_ids.update(grant.tool_ids)
                effect_ids.update(grant.effect_ids)
        if session_key:
            for grant in repository.list_for_session(session_key):
                tool_ids.update(grant.tool_ids)
                effect_ids.update(grant.effect_ids)
        return GrantedAuthorizationPayload(
            tool_ids=tuple(sorted(tool_ids)),
            effect_ids=tuple(sorted(effect_ids)),
        )

    def upsert_policy(
        self,
        policy: AuthorizationPolicy,
        *,
        actor_type: str | None = None,
        actor_id: str | None = None,
        reason: str = "",
    ) -> AuthorizationPolicy:
        before = self.policy_repository.get(policy.id)
        self.policy_repository.upsert(policy)
        self._invalidate_policy_snapshot()
        self._record_audit(
            action="policy.upsert",
            status="succeeded",
            actor_type=actor_type,
            actor_id=actor_id,
            target_policy_id=policy.id,
            reason=reason,
            before_payload=_policy_payload(before) if before is not None else {},
            after_payload=_policy_payload(policy),
        )
        return policy

    def create_policy(
        self,
        policy: AuthorizationPolicy,
        *,
        actor_type: str | None = None,
        actor_id: str | None = None,
        reason: str = "",
    ) -> AuthorizationPolicy:
        if self.policy_repository.get(policy.id) is not None:
            raise ValueError(f"Authorization policy '{policy.id}' already exists.")
        self.policy_repository.upsert(policy)
        self._invalidate_policy_snapshot()
        self._record_audit(
            action="policy.create",
            status="succeeded",
            actor_type=actor_type,
            actor_id=actor_id,
            target_policy_id=policy.id,
            reason=reason,
            after_payload=_policy_payload(policy),
        )
        return policy

    def update_policy(
        self,
        policy: AuthorizationPolicy,
        *,
        actor_type: str | None = None,
        actor_id: str | None = None,
        reason: str = "",
    ) -> AuthorizationPolicy:
        before = self.policy_repository.get(policy.id)
        if before is None:
            raise AuthorizationPolicyNotFoundError(
                f"Authorization policy '{policy.id}' was not found.",
            )
        self.policy_repository.upsert(policy)
        self._invalidate_policy_snapshot()
        self._record_audit(
            action="policy.update",
            status="succeeded",
            actor_type=actor_type,
            actor_id=actor_id,
            target_policy_id=policy.id,
            reason=reason,
            before_payload=_policy_payload(before),
            after_payload=_policy_payload(policy),
        )
        return policy

    def set_policy_enabled(
        self,
        policy_id: str,
        *,
        enabled: bool,
        actor_type: str | None = None,
        actor_id: str | None = None,
        reason: str = "",
    ) -> AuthorizationPolicy:
        before = self.policy_repository.get(policy_id)
        if before is None:
            raise AuthorizationPolicyNotFoundError(
                f"Authorization policy '{policy_id}' was not found.",
            )
        after = replace(before, enabled=enabled)
        self.policy_repository.upsert(after)
        self._invalidate_policy_snapshot()
        self._record_audit(
            action="policy.enable" if enabled else "policy.disable",
            status="succeeded",
            actor_type=actor_type,
            actor_id=actor_id,
            target_policy_id=policy_id,
            reason=reason,
            before_payload=_policy_payload(before),
            after_payload=_policy_payload(after),
        )
        return after

    def delete_policy(
        self,
        policy_id: str,
        *,
        actor_type: str | None = None,
        actor_id: str | None = None,
        reason: str = "",
    ) -> AuthorizationPolicy:
        before = self.policy_repository.get(policy_id)
        if before is None:
            raise AuthorizationPolicyNotFoundError(
                f"Authorization policy '{policy_id}' was not found.",
            )
        self.policy_repository.delete(policy_id)
        self._invalidate_policy_snapshot()
        self._record_audit(
            action="policy.delete",
            status="succeeded",
            actor_type=actor_type,
            actor_id=actor_id,
            target_policy_id=policy_id,
            reason=reason,
            before_payload=_policy_payload(before),
        )
        return before

    def import_policies(
        self,
        policies: tuple[AuthorizationPolicy, ...],
        *,
        actor_type: str | None = None,
        actor_id: str | None = None,
        reason: str = "",
        source: str = "inline",
    ) -> tuple[AuthorizationPolicy, ...]:
        imported: list[AuthorizationPolicy] = []
        before_by_id = {
            policy.id: _policy_payload(policy)
            for policy in self.policy_repository.list()
            if policy.id in {item.id for item in policies}
        }
        for policy in policies:
            self.policy_repository.upsert(policy)
            imported.append(policy)
        self._invalidate_policy_snapshot()
        self._record_audit(
            action="policy.import",
            status="succeeded",
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
            before_payload={"policies": before_by_id},
            after_payload={
                "policies": {
                    policy.id: _policy_payload(policy)
                    for policy in imported
                },
            },
            metadata={
                "source": source,
                "imported_policy_ids": [policy.id for policy in imported],
                "count": len(imported),
            },
        )
        return tuple(imported)

    def export_policy_bundle(self) -> dict[str, Any]:
        return {
            "kind": "authorization.policy_bundle",
            "version": 1,
            "policies": [
                _policy_payload(policy)
                for policy in self._policy_snapshot()
            ],
        }

    def dry_run(
        self,
        request: AuthorizationRequest,
        *,
        policies: tuple[AuthorizationPolicy, ...] | None = None,
        actor_type: str | None = None,
        actor_id: str | None = None,
        reason: str = "",
    ) -> AuthorizationDecision:
        decision = self.evaluator.evaluate(
            request,
            list(policies if policies is not None else self._policy_snapshot()),
        )
        self._record_audit(
            action="decision.dry_run",
            status="succeeded",
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
            decision_payload=_decision_payload(decision),
            metadata={"request": _request_payload(request)},
        )
        return decision

    def preview_policy_impact(
        self,
        request: AuthorizationRequest,
        *,
        proposed_policies: tuple[AuthorizationPolicy, ...] = (),
        remove_policy_ids: tuple[str, ...] = (),
        actor_type: str | None = None,
        actor_id: str | None = None,
        reason: str = "",
    ) -> AuthorizationImpactPreview:
        current_policies = list(self._policy_snapshot())
        before = self.evaluator.evaluate(request, current_policies)

        remove_ids = {
            policy_id.strip()
            for policy_id in remove_policy_ids
            if policy_id.strip()
        }
        proposed_by_id = {policy.id: policy for policy in proposed_policies}
        current_by_id = {policy.id: policy for policy in current_policies}
        next_policies = [
            proposed_by_id.get(policy.id, policy)
            for policy in current_policies
            if policy.id not in remove_ids
        ]
        next_policies.extend(
            policy
            for policy in proposed_policies
            if policy.id not in current_by_id
        )
        after = self.evaluator.evaluate(request, next_policies)
        added_ids = tuple(
            sorted(policy.id for policy in proposed_policies if policy.id not in current_by_id),
        )
        updated_ids = tuple(
            sorted(policy.id for policy in proposed_policies if policy.id in current_by_id),
        )
        removed_ids = tuple(sorted(remove_ids))
        preview = AuthorizationImpactPreview(
            before=before,
            after=after,
            changed=_decision_payload(before) != _decision_payload(after),
            added_policy_ids=added_ids,
            updated_policy_ids=updated_ids,
            removed_policy_ids=removed_ids,
        )
        self._record_audit(
            action="decision.impact_preview",
            status="succeeded",
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
            before_payload={"decision": _decision_payload(before)},
            after_payload={"decision": _decision_payload(after)},
            metadata={
                "request": _request_payload(request),
                "added_policy_ids": list(added_ids),
                "updated_policy_ids": list(updated_ids),
                "removed_policy_ids": list(removed_ids),
                "changed": preview.changed,
            },
        )
        return preview

    def list_audit_records(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        action: str | None = None,
        target_policy_id: str | None = None,
    ) -> list[AuthorizationAuditRecord]:
        if self.audit_repository is None:
            return []
        return self.audit_repository.list(
            limit=limit,
            offset=offset,
            action=action,
            target_policy_id=target_policy_id,
        )

    def grant_agent_effect_authorization(
        self,
        *,
        agent_id: str,
        effect_id: str,
        actor_type: str | None = None,
        actor_id: str | None = None,
        reason: str = "",
    ) -> AuthorizationPolicy:
        agent = agent_id.strip()
        effect = effect_id.strip()
        if not agent:
            raise ValueError("agent_id cannot be empty.")
        if not effect:
            raise ValueError("effect_id cannot be empty.")
        return self.upsert_policy(
            AuthorizationPolicy(
                id=_agent_effect_policy_id(agent, effect),
                description=f"Allow agent '{agent}' to authorize effect '{effect}'.",
                effect=AuthorizationEffect.ALLOW,
                actions=("tool.effect.authorize",),
                resource_kind="tool",
                resource_match={"authorization_effect_ids": [effect]},
                context_match={"agent_id": agent},
                priority=1000,
                enabled=True,
                source_kind="local_managed",
            ),
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
        )

    def grant_agent_tool_authorization(
        self,
        *,
        agent_id: str,
        tool_id: str,
        actor_type: str | None = None,
        actor_id: str | None = None,
        reason: str = "",
    ) -> AuthorizationPolicy:
        agent = agent_id.strip()
        tool = tool_id.strip()
        if not agent:
            raise ValueError("agent_id cannot be empty.")
        if not tool:
            raise ValueError("tool_id cannot be empty.")
        return self.upsert_policy(
            AuthorizationPolicy(
                id=_agent_tool_authorization_policy_id(agent, tool),
                description=f"Allow agent '{agent}' to authorize tool '{tool}'.",
                effect=AuthorizationEffect.ALLOW,
                actions=("tool.authorize",),
                resource_kind="tool",
                resource_id=tool,
                context_match={"agent_id": agent},
                priority=1000,
                enabled=True,
                source_kind="local_managed",
            ),
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
        )

    def revoke_agent_effect_authorization(
        self,
        *,
        agent_id: str,
        effect_id: str,
        actor_type: str | None = None,
        actor_id: str | None = None,
        reason: str = "",
    ) -> AuthorizationPolicy | None:
        agent = agent_id.strip()
        effect = effect_id.strip()
        if not agent:
            raise ValueError("agent_id cannot be empty.")
        if not effect:
            raise ValueError("effect_id cannot be empty.")
        return self._delete_agent_managed_policy(
            _agent_effect_policy_id(agent, effect),
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
        )

    def revoke_agent_tool_authorization(
        self,
        *,
        agent_id: str,
        tool_id: str,
        actor_type: str | None = None,
        actor_id: str | None = None,
        reason: str = "",
    ) -> AuthorizationPolicy | None:
        agent = agent_id.strip()
        tool = tool_id.strip()
        if not agent:
            raise ValueError("agent_id cannot be empty.")
        if not tool:
            raise ValueError("tool_id cannot be empty.")
        return self._delete_agent_managed_policy(
            _agent_tool_authorization_policy_id(agent, tool),
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
        )

    def _delete_agent_managed_policy(
        self,
        policy_id: str,
        *,
        actor_type: str | None,
        actor_id: str | None,
        reason: str,
    ) -> AuthorizationPolicy | None:
        policy = self.policy_repository.get(policy_id)
        if policy is None:
            return None
        if policy.source_kind != "local_managed":
            raise ValueError(
                f"Authorization policy '{policy_id}' is not a local managed agent grant.",
            )
        return self.delete_policy(
            policy_id,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
        )

    def _record_audit(
        self,
        *,
        action: str,
        status: str,
        actor_type: str | None = None,
        actor_id: str | None = None,
        target_policy_id: str | None = None,
        reason: str = "",
        before_payload: dict[str, Any] | None = None,
        after_payload: dict[str, Any] | None = None,
        decision_payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self.audit_repository is None:
            return
        self.audit_repository.add(
            AuthorizationAuditRecord(
                id=uuid4().hex,
                action=action,
                status=status,
                actor_type=(actor_type or "").strip() or None,
                actor_id=(actor_id or "").strip() or None,
                target_policy_id=(target_policy_id or "").strip() or None,
                reason=reason.strip(),
                before_payload=dict(before_payload or {}),
                after_payload=dict(after_payload or {}),
                decision_payload=dict(decision_payload or {}),
                metadata=dict(metadata or {}),
                created_at=datetime.now(timezone.utc),
            ),
        )


def _agent_effect_policy_id(agent_id: str, effect_id: str) -> str:
    def _clean(value: str) -> str:
        return "".join(char if char.isalnum() else "_" for char in value)

    return f"local_allow_agent_effect__{_clean(agent_id)}__{_clean(effect_id)}"


def _agent_tool_authorization_policy_id(agent_id: str, tool_id: str) -> str:
    def _clean(value: str) -> str:
        return "".join(char if char.isalnum() else "_" for char in value)

    return f"local_allow_agent_tool__{_clean(agent_id)}__{_clean(tool_id)}"


def _normalize_values(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            value.strip()
            for value in values
            if value is not None and value.strip()
        ),
    )


def _run_grant_id(run_id: str, approval_request_id: str | None) -> str:
    request_id = (approval_request_id or "").strip() or "manual"
    return f"run:{run_id}:{request_id}"


def _session_grant_id(session_key: str, approval_request_id: str | None) -> str:
    request_id = (approval_request_id or "").strip() or "manual"
    return f"session:{session_key}:{request_id}"


def _policy_payload(policy: AuthorizationPolicy) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": policy.id,
        "description": policy.description,
        "effect": policy.effect.value,
        "actions": list(policy.actions),
        "priority": policy.priority,
        "enabled": policy.enabled,
        "source_kind": policy.source_kind,
    }
    subject: dict[str, Any] = {}
    if policy.subject_type is not None:
        subject["type"] = policy.subject_type
    if policy.subject_id is not None:
        subject["id"] = policy.subject_id
    if policy.subject_match:
        subject["match"] = dict(policy.subject_match)
    if subject:
        payload["subject"] = subject

    resource: dict[str, Any] = {}
    if policy.resource_kind is not None:
        resource["kind"] = policy.resource_kind
    if policy.resource_id is not None:
        resource["id"] = policy.resource_id
    if policy.resource_match:
        resource["match"] = dict(policy.resource_match)
    if resource:
        payload["resource"] = resource

    if policy.context_match:
        payload["context"] = {"match": dict(policy.context_match)}
    if policy.condition is not None:
        payload["condition"] = dict(policy.condition)
    if policy.obligations:
        payload["obligations"] = [
            (
                {"name": obligation.name, "params": dict(obligation.params)}
                if obligation.params
                else obligation.name
            )
            for obligation in policy.obligations
        ]
    return payload


def _decision_payload(decision: AuthorizationDecision) -> dict[str, Any]:
    return {
        "allowed": decision.allowed,
        "reason": decision.reason,
        "code": decision.code.value,
        "matched_policy_ids": list(decision.matched_policy_ids),
        "obligations": [
            {"name": obligation.name, "params": dict(obligation.params)}
            for obligation in decision.obligations
        ],
        "details": dict(decision.details),
    }


def _request_payload(request: AuthorizationRequest) -> dict[str, Any]:
    return {
        "subject": {
            "type": request.subject.type,
            "id": request.subject.id,
            "attrs": dict(request.subject.attrs),
        },
        "action": request.action,
        "resource": {
            "kind": request.resource.kind,
            "id": request.resource.id,
            "attrs": dict(request.resource.attrs),
        },
        "context": {"attrs": dict(request.context.attrs)},
    }


def _grant_payload(grant: TemporaryAuthorizationGrant) -> dict[str, Any]:
    return {
        "id": grant.id,
        "scope": grant.scope.value,
        "run_id": grant.run_id,
        "session_key": grant.session_key,
        "agent_id": grant.agent_id,
        "approval_request_id": grant.approval_request_id,
        "effect_ids": list(grant.effect_ids),
        "tool_ids": list(grant.tool_ids),
        "created_at": grant.created_at.isoformat(),
    }
