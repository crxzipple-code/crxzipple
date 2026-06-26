from __future__ import annotations

from typing import Callable

from crxzipple.modules.authorization.domain import (
    AuthorizationDecision,
    AuthorizationPolicy,
    AuthorizationRequest,
)

from .payloads import (
    decision_payload,
    request_payload,
)
from .policy_impact import (
    AuthorizationImpactPreview,
    build_policy_impact_preview,
)


class AuthorizationDecisionUseCases:
    def __init__(
        self,
        *,
        evaluate: Callable[
            [AuthorizationRequest, list[AuthorizationPolicy]],
            AuthorizationDecision,
        ],
        policy_snapshot: Callable[[], tuple[AuthorizationPolicy, ...]],
        record_audit: Callable[..., None],
    ) -> None:
        self._evaluate = evaluate
        self._policy_snapshot = policy_snapshot
        self._record_audit = record_audit

    def dry_run(
        self,
        request: AuthorizationRequest,
        *,
        policies: tuple[AuthorizationPolicy, ...] | None = None,
        actor_type: str | None = None,
        actor_id: str | None = None,
        reason: str = "",
    ) -> AuthorizationDecision:
        decision = self._evaluate(
            request,
            list(policies if policies is not None else self._policy_snapshot()),
        )
        self._record_audit(
            action="decision.dry_run",
            status="succeeded",
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
            decision_payload=decision_payload(decision),
            metadata={"request": request_payload(request)},
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
        preview = build_policy_impact_preview(
            request,
            current_policies=self._policy_snapshot(),
            proposed_policies=proposed_policies,
            remove_policy_ids=remove_policy_ids,
            evaluate=self._evaluate,
        )
        self._record_audit(
            action="decision.impact_preview",
            status="succeeded",
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
            before_payload={"decision": decision_payload(preview.before)},
            after_payload={"decision": decision_payload(preview.after)},
            metadata={
                "request": request_payload(request),
                "added_policy_ids": list(preview.added_policy_ids),
                "updated_policy_ids": list(preview.updated_policy_ids),
                "removed_policy_ids": list(preview.removed_policy_ids),
                "changed": preview.changed,
            },
        )
        return preview


__all__ = ["AuthorizationDecisionUseCases"]
