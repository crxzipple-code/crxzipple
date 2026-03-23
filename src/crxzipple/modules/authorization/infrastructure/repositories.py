from __future__ import annotations

from dataclasses import dataclass, field

from crxzipple.modules.authorization.domain import AuthorizationPolicy


@dataclass(slots=True)
class InMemoryAuthorizationPolicyRepository:
    policies: list[AuthorizationPolicy] = field(default_factory=list)

    def list(self) -> list[AuthorizationPolicy]:
        return sorted(
            self.policies,
            key=lambda policy: (-policy.priority, policy.id),
        )

