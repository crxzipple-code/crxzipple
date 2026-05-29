from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Protocol

from crxzipple.modules.memory.domain import (
    MemoryPolicy,
    MemoryPolicyStatus,
    MemoryPolicyTargetKind,
)


@dataclass(frozen=True, slots=True)
class MemoryRuntimePolicy:
    recall_enabled: bool = True
    remember_enabled: bool = True
    max_recall_items: int = 6
    retention: str = "engine_default"

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_recall_items", max(1, int(self.max_recall_items)))
        object.__setattr__(self, "retention", self.retention.strip() or "engine_default")


class MemoryPolicyRepository(Protocol):
    def get(self, policy_id: str) -> MemoryPolicy | None:
        ...

    def list(self, *, include_disabled: bool = False) -> tuple[MemoryPolicy, ...]:
        ...

    def upsert(self, policy: MemoryPolicy) -> MemoryPolicy:
        ...

    def delete(self, policy_id: str) -> None:
        ...


class MemoryPolicyProvider(Protocol):
    def effective_policy_for_scope(
        self,
        *,
        scope_ref: str,
        agent_id: str | None = None,
    ) -> MemoryRuntimePolicy:
        ...


class MemoryPolicyService:
    def __init__(self, repository: MemoryPolicyRepository) -> None:
        self._repository = repository

    def upsert_policy(
        self,
        *,
        policy_id: str,
        target_kind: MemoryPolicyTargetKind,
        target_id: str | None = None,
        recall_enabled: bool = True,
        remember_enabled: bool = True,
        max_recall_items: int = 6,
        retention: str = "engine_default",
        status: MemoryPolicyStatus = "active",
        metadata: dict[str, object] | None = None,
    ) -> MemoryPolicy:
        now = datetime.now(timezone.utc)
        existing = self._repository.get(policy_id)
        policy = MemoryPolicy(
            policy_id=policy_id,
            target_kind=target_kind,
            target_id=target_id,
            recall_enabled=recall_enabled,
            remember_enabled=remember_enabled,
            max_recall_items=max_recall_items,
            retention=retention,
            status=status,
            metadata=metadata or {},
            created_at=existing.created_at if existing is not None else now,
            updated_at=now,
        )
        return self._repository.upsert(policy)

    def get_policy(self, policy_id: str) -> MemoryPolicy | None:
        normalized = policy_id.strip()
        if not normalized:
            return None
        return self._repository.get(normalized)

    def list_policies(
        self,
        *,
        include_disabled: bool = False,
    ) -> tuple[MemoryPolicy, ...]:
        return self._repository.list(include_disabled=include_disabled)

    def disable_policy(self, policy_id: str) -> MemoryPolicy | None:
        policy = self.get_policy(policy_id)
        if policy is None:
            return None
        return self._repository.upsert(
            replace(
                policy,
                status="disabled",
                updated_at=datetime.now(timezone.utc),
            ),
        )

    def delete_policy(self, policy_id: str) -> None:
        self._repository.delete(policy_id.strip())

    def effective_policy_for_scope(
        self,
        *,
        scope_ref: str,
        agent_id: str | None = None,
    ) -> MemoryRuntimePolicy:
        normalized_scope = scope_ref.strip()
        normalized_agent = agent_id.strip() if agent_id else None
        effective = MemoryRuntimePolicy()
        policies = sorted(
            self._repository.list(include_disabled=False),
            key=_policy_sort_key,
        )
        for policy in policies:
            if not _matches_policy(
                policy,
                scope_ref=normalized_scope,
                agent_id=normalized_agent,
            ):
                continue
            retention = (
                policy.retention
                if policy.retention != "engine_default"
                else effective.retention
            )
            effective = MemoryRuntimePolicy(
                recall_enabled=effective.recall_enabled and policy.recall_enabled,
                remember_enabled=effective.remember_enabled and policy.remember_enabled,
                max_recall_items=min(effective.max_recall_items, policy.max_recall_items),
                retention=retention,
            )
        return effective


def _policy_sort_key(policy: MemoryPolicy) -> tuple[int, str]:
    priority = {"global": 0, "space": 1, "agent": 2}
    return (priority[policy.target_kind], policy.policy_id)


def _matches_policy(
    policy: MemoryPolicy,
    *,
    scope_ref: str,
    agent_id: str | None,
) -> bool:
    if policy.target_kind == "global":
        return True
    if policy.target_kind == "space":
        return policy.target_id == scope_ref
    if policy.target_kind == "agent":
        return policy.target_id == agent_id
    return False
