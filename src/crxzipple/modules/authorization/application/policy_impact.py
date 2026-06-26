from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from crxzipple.modules.authorization.domain import (
    AuthorizationDecision,
    AuthorizationPolicy,
    AuthorizationRequest,
)

from .payloads import decision_payload


@dataclass(frozen=True, slots=True)
class AuthorizationImpactPreview:
    before: AuthorizationDecision
    after: AuthorizationDecision
    changed: bool
    added_policy_ids: tuple[str, ...] = ()
    updated_policy_ids: tuple[str, ...] = ()
    removed_policy_ids: tuple[str, ...] = ()


def build_policy_impact_preview(
    request: AuthorizationRequest,
    *,
    current_policies: Sequence[AuthorizationPolicy],
    proposed_policies: tuple[AuthorizationPolicy, ...],
    remove_policy_ids: tuple[str, ...],
    evaluate: Callable[
        [AuthorizationRequest, list[AuthorizationPolicy]],
        AuthorizationDecision,
    ],
) -> AuthorizationImpactPreview:
    current_policy_list = list(current_policies)
    before = evaluate(request, current_policy_list)

    remove_ids = {
        policy_id.strip()
        for policy_id in remove_policy_ids
        if policy_id.strip()
    }
    proposed_by_id = {policy.id: policy for policy in proposed_policies}
    current_by_id = {policy.id: policy for policy in current_policy_list}
    next_policies = [
        proposed_by_id.get(policy.id, policy)
        for policy in current_policy_list
        if policy.id not in remove_ids
    ]
    next_policies.extend(
        policy
        for policy in proposed_policies
        if policy.id not in current_by_id
    )
    after = evaluate(request, next_policies)
    added_ids = tuple(
        sorted(policy.id for policy in proposed_policies if policy.id not in current_by_id),
    )
    updated_ids = tuple(
        sorted(policy.id for policy in proposed_policies if policy.id in current_by_id),
    )
    removed_ids = tuple(sorted(remove_ids))
    return AuthorizationImpactPreview(
        before=before,
        after=after,
        changed=decision_payload(before) != decision_payload(after),
        added_policy_ids=added_ids,
        updated_policy_ids=updated_ids,
        removed_policy_ids=removed_ids,
    )
