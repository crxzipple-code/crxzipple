from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.authorization.domain import (
    AuthorizationDecision,
    AuthorizationDeniedError,
    AuthorizationPolicy,
    AuthorizationPolicyRepository,
    AuthorizationRequest,
)


class AuthorizationEvaluator:
    def evaluate(
        self,
        request: AuthorizationRequest,
        policies: list[AuthorizationPolicy],
    ) -> AuthorizationDecision:
        raise NotImplementedError


@dataclass(slots=True)
class AuthorizationApplicationService:
    policy_repository: AuthorizationPolicyRepository
    evaluator: AuthorizationEvaluator
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
            )
        return self.evaluator.evaluate(request, self.policy_repository.list())

    def authorize(self, request: AuthorizationRequest) -> AuthorizationDecision:
        decision = self.check(request)
        if not decision.allowed:
            raise AuthorizationDeniedError(decision.reason)
        return decision

