from __future__ import annotations

from crxzipple.modules.authorization.domain import (
    AuthorizationDecision,
    AuthorizationPolicy,
    AuthorizationRequest,
)

from .policy_impact import AuthorizationImpactPreview


class AuthorizationDecisionFacadeMixin:
    def dry_run(
        self,
        request: AuthorizationRequest,
        *,
        policies: tuple[AuthorizationPolicy, ...] | None = None,
        actor_type: str | None = None,
        actor_id: str | None = None,
        reason: str = "",
    ) -> AuthorizationDecision:
        return self._decision_use_cases().dry_run(
            request,
            policies=policies,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
        )

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
        return self._decision_use_cases().preview_policy_impact(
            request,
            proposed_policies=proposed_policies,
            remove_policy_ids=remove_policy_ids,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
        )
