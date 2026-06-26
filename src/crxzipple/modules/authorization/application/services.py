from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from crxzipple.modules.authorization.domain import (
    AuthorizationAuditRepository,
    AuthorizationDecision,
    AuthorizationDecisionCode,
    AuthorizationDeniedError,
    AuthorizationPolicy,
    AuthorizationPolicyRepository,
    AuthorizationRequest,
    TemporaryAuthorizationGrantRepository,
    ToolExecutionAuthorizationRequest,
)

from .audit_records import build_authorization_audit_record
from .agent_grants import AgentAuthorizationGrantService
from .decision_use_cases import AuthorizationDecisionUseCases
from .policy_lifecycle import AuthorizationPolicyLifecycle
from .service_audit_facade import AuthorizationAuditFacadeMixin
from .service_decision_facade import AuthorizationDecisionFacadeMixin
from .service_grant_facade import AuthorizationGrantFacadeMixin
from .service_policy_facade import AuthorizationPolicyFacadeMixin
from .temporary_grants import (
    collect_temporary_granted_authorization,
)
from .temporary_grant_service import TemporaryAuthorizationGrantService
from .tool_execution_authorization import (
    check_tool_execution_authorization,
)


class AuthorizationEvaluator:
    def evaluate(
        self,
        request: AuthorizationRequest,
        policies: list[AuthorizationPolicy],
    ) -> AuthorizationDecision:
        raise NotImplementedError


@dataclass(slots=True)
class AuthorizationApplicationService(
    AuthorizationPolicyFacadeMixin,
    AuthorizationDecisionFacadeMixin,
    AuthorizationGrantFacadeMixin,
    AuthorizationAuditFacadeMixin,
):
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
        return check_tool_execution_authorization(
            request,
            temporary_authorization=collect_temporary_granted_authorization(
                dict(request.context.attrs),
                self.temporary_grant_repository_factory,
            ),
            evaluate_request=self._evaluate_for_tool_execution,
        )

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

    def _policy_lifecycle(self) -> AuthorizationPolicyLifecycle:
        return AuthorizationPolicyLifecycle(
            policy_repository=self.policy_repository,
            record_audit=self._record_audit,
            invalidate_policy_snapshot=self._invalidate_policy_snapshot,
        )

    def _agent_grants(self) -> AgentAuthorizationGrantService:
        return AgentAuthorizationGrantService(
            policy_repository=self.policy_repository,
            policy_lifecycle=self._policy_lifecycle(),
        )

    def _temporary_grants(self) -> TemporaryAuthorizationGrantService:
        return TemporaryAuthorizationGrantService(
            repository_factory=self.temporary_grant_repository_factory,
            record_audit=self._record_audit,
        )

    def _decision_use_cases(self) -> AuthorizationDecisionUseCases:
        return AuthorizationDecisionUseCases(
            evaluate=self.evaluator.evaluate,
            policy_snapshot=self._policy_snapshot,
            record_audit=self._record_audit,
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
            build_authorization_audit_record(
                action=action,
                status=status,
                actor_type=(actor_type or "").strip() or None,
                actor_id=(actor_id or "").strip() or None,
                target_policy_id=(target_policy_id or "").strip() or None,
                reason=reason.strip(),
                before_payload=before_payload,
                after_payload=after_payload,
                decision_payload=decision_payload,
                metadata=metadata,
            ),
        )
