from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from crxzipple.modules.authorization.domain import (
    AuthorizationPolicy,
    AuthorizationPolicyNotFoundError,
    AuthorizationPolicyRepository,
)

from .payloads import policy_payload as _policy_payload


RecordAuthorizationAudit = Callable[..., None]


@dataclass(slots=True)
class AuthorizationPolicyLifecycle:
    policy_repository: AuthorizationPolicyRepository
    record_audit: RecordAuthorizationAudit
    invalidate_policy_snapshot: Callable[[], None]

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
        self.invalidate_policy_snapshot()
        self.record_audit(
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
        self.invalidate_policy_snapshot()
        self.record_audit(
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
        self.invalidate_policy_snapshot()
        self.record_audit(
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
        self.invalidate_policy_snapshot()
        self.record_audit(
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
        self.invalidate_policy_snapshot()
        self.record_audit(
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
        policy_ids = {item.id for item in policies}
        before_by_id = {
            policy.id: _policy_payload(policy)
            for policy in self.policy_repository.list()
            if policy.id in policy_ids
        }
        for policy in policies:
            self.policy_repository.upsert(policy)
            imported.append(policy)
        self.invalidate_policy_snapshot()
        self.record_audit(
            action="policy.import",
            status="succeeded",
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
            before_payload={"policies": before_by_id},
            after_payload={
                "policies": {policy.id: _policy_payload(policy) for policy in imported},
            },
            metadata={
                "source": source,
                "imported_policy_ids": [policy.id for policy in imported],
                "count": len(imported),
            },
        )
        return tuple(imported)


__all__ = ["AuthorizationPolicyLifecycle", "RecordAuthorizationAudit"]
