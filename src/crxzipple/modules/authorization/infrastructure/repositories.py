from __future__ import annotations

from dataclasses import dataclass, field

from crxzipple.modules.authorization.domain import AuthorizationPolicy


@dataclass(slots=True)
class InMemoryAuthorizationPolicyRepository:
    policies: list[AuthorizationPolicy] = field(default_factory=list)

    def get(self, policy_id: str) -> AuthorizationPolicy | None:
        return next(
            (policy for policy in self.policies if policy.id == policy_id),
            None,
        )

    def list(self) -> list[AuthorizationPolicy]:
        return sorted(
            self.policies,
            key=lambda policy: (-policy.priority, policy.id),
        )

    def upsert(self, policy: AuthorizationPolicy) -> None:
        for index, existing in enumerate(self.policies):
            if existing.id == policy.id:
                self.policies[index] = policy
                break
        else:
            self.policies.append(policy)

    def delete(self, policy_id: str) -> bool:
        before_count = len(self.policies)
        self.policies = [
            policy
            for policy in self.policies
            if policy.id != policy_id
        ]
        return len(self.policies) != before_count
