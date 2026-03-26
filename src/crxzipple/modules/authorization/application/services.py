from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from crxzipple.modules.authorization.domain import (
    AuthorizationContext,
    AuthorizationDecision,
    AuthorizationDecisionCode,
    AuthorizationDeniedError,
    AuthorizationEffect,
    AuthorizationGrantScope,
    AuthorizationPolicy,
    AuthorizationPolicyRepository,
    AuthorizationRequest,
    AuthorizationResource,
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
class GrantedAccessPayload:
    tool_ids: tuple[str, ...] = ()
    effect_ids: tuple[str, ...] = ()


@dataclass(slots=True)
class AuthorizationApplicationService:
    policy_repository: AuthorizationPolicyRepository
    evaluator: AuthorizationEvaluator
    temporary_grant_repository_factory: Callable[[], TemporaryAuthorizationGrantRepository] | None = None
    enabled: bool = False

    def is_enabled(self) -> bool:
        return self.enabled

    def list_policies(self) -> list[AuthorizationPolicy]:
        return self.policy_repository.list()

    def check(self, request: AuthorizationRequest) -> AuthorizationDecision:
        if not self.enabled:
            return AuthorizationDecision(
                allowed=True,
                reason="authorization disabled",
                code=AuthorizationDecisionCode.AUTHORIZATION_DISABLED,
            )
        return self.evaluator.evaluate(request, self.policy_repository.list())

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
        temporary_access = self._temporary_granted_access(context_attrs)
        granted_tool_ids = tuple(
            tool_id.strip()
            for tool_id in (*request.granted_tool_ids, *temporary_access.tool_ids)
            if tool_id is not None and tool_id.strip()
        )
        granted_effect_ids = tuple(
            effect_id.strip()
            for effect_id in (*request.granted_effect_ids, *temporary_access.effect_ids)
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
                action="tool.access_tool",
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
                    action="tool.access_effect",
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
                    f"Tool execution allowed because temporary access was granted for '{request.resource.id}'."
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

    def grant_run_access(
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
        return grant

    def grant_session_access(
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
        return self.evaluator.evaluate(request, self.policy_repository.list())

    def _store_temporary_grant(
        self,
        grant: TemporaryAuthorizationGrant,
    ) -> None:
        if self.temporary_grant_repository_factory is None:
            return
        repository = self.temporary_grant_repository_factory()
        repository.add(grant)

    def _temporary_granted_access(
        self,
        context_attrs: dict[str, object],
    ) -> GrantedAccessPayload:
        if self.temporary_grant_repository_factory is None:
            return GrantedAccessPayload()
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
        return GrantedAccessPayload(
            tool_ids=tuple(sorted(tool_ids)),
            effect_ids=tuple(sorted(effect_ids)),
        )

    def upsert_policy(self, policy: AuthorizationPolicy) -> AuthorizationPolicy:
        self.policy_repository.upsert(policy)
        return policy

    def grant_agent_effect_access(
        self,
        *,
        agent_id: str,
        effect_id: str,
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
                description=f"Allow agent '{agent}' to access effect '{effect}'.",
                effect=AuthorizationEffect.ALLOW,
                actions=("tool.access_effect",),
                resource_kind="tool",
                resource_match={"authorization_effect_ids": [effect]},
                context_match={"agent_id": agent},
                priority=1000,
                enabled=True,
                source_kind="local_managed",
            ),
        )

    def grant_agent_tool_access(
        self,
        *,
        agent_id: str,
        tool_id: str,
    ) -> AuthorizationPolicy:
        agent = agent_id.strip()
        tool = tool_id.strip()
        if not agent:
            raise ValueError("agent_id cannot be empty.")
        if not tool:
            raise ValueError("tool_id cannot be empty.")
        return self.upsert_policy(
            AuthorizationPolicy(
                id=_agent_tool_access_policy_id(agent, tool),
                description=f"Allow agent '{agent}' to access tool '{tool}'.",
                effect=AuthorizationEffect.ALLOW,
                actions=("tool.access_tool",),
                resource_kind="tool",
                resource_id=tool,
                context_match={"agent_id": agent},
                priority=1000,
                enabled=True,
                source_kind="local_managed",
            ),
        )


def _agent_effect_policy_id(agent_id: str, effect_id: str) -> str:
    def _clean(value: str) -> str:
        return "".join(char if char.isalnum() else "_" for char in value)

    return f"local_allow_agent_effect__{_clean(agent_id)}__{_clean(effect_id)}"


def _agent_tool_access_policy_id(agent_id: str, tool_id: str) -> str:
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
