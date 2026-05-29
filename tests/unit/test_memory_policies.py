from __future__ import annotations

from dataclasses import dataclass
import unittest

from crxzipple.modules.memory import (
    MemoryActorContext,
    MemoryPolicyService,
    MemoryRecallRequest,
    MemoryRecallResult,
    MemoryRememberRequest,
    MemoryRememberResult,
    MemoryRuntimeService,
    MemoryUseContext,
)
from crxzipple.modules.memory.application import (
    MemoryEngineCapabilities,
    MemoryResolvedLayer,
)
from crxzipple.modules.memory.domain import MemoryPolicy


class _InMemoryMemoryPolicyRepository:
    def __init__(self) -> None:
        self.policies: dict[str, MemoryPolicy] = {}

    def get(self, policy_id: str) -> MemoryPolicy | None:
        return self.policies.get(policy_id)

    def list(self, *, include_disabled: bool = False) -> tuple[MemoryPolicy, ...]:
        values = self.policies.values()
        if not include_disabled:
            values = [policy for policy in values if policy.enabled]
        return tuple(sorted(values, key=lambda item: item.policy_id))

    def upsert(self, policy: MemoryPolicy) -> MemoryPolicy:
        self.policies[policy.policy_id] = policy
        return policy

    def delete(self, policy_id: str) -> None:
        self.policies.pop(policy_id, None)


@dataclass(frozen=True, slots=True)
class _StaticScopeResolver:
    context: MemoryUseContext

    def resolve(self, space_ref: str | None) -> MemoryUseContext | None:
        if space_ref == self.context.space_id:
            return self.context
        return None


class _CapturingMemoryEngine:
    engine_id = "fake"

    def __init__(self) -> None:
        self.recall_request: MemoryRecallRequest | None = None
        self.remember_request: MemoryRememberRequest | None = None

    def capabilities(self) -> MemoryEngineCapabilities:
        return MemoryEngineCapabilities()

    def recall(
        self,
        *,
        layers: tuple[MemoryResolvedLayer, ...],
        request: MemoryRecallRequest,
    ) -> MemoryRecallResult:
        self.recall_request = request
        return MemoryRecallResult(
            scope=layers[0].as_scope(),
            items=(),
            query=request.query,
            searched_layers=layers,
        )

    def remember(
        self,
        *,
        layer: MemoryResolvedLayer,
        request: MemoryRememberRequest,
    ) -> MemoryRememberResult:
        self.remember_request = request
        return MemoryRememberResult(
            scope=layer.as_scope(),
            status="remembered",
            target_layer=layer,
        )


class MemoryPolicyServiceTestCase(unittest.TestCase):
    def test_effective_policy_prefers_space_policy_over_global_default(self) -> None:
        service = MemoryPolicyService(_InMemoryMemoryPolicyRepository())
        service.upsert_policy(
            policy_id="global-memory",
            target_kind="global",
            recall_enabled=True,
            remember_enabled=True,
            max_recall_items=5,
        )
        service.upsert_policy(
            policy_id="assistant-memory",
            target_kind="space",
            target_id="assistant",
            recall_enabled=True,
            remember_enabled=False,
            max_recall_items=2,
        )

        assistant_policy = service.effective_policy_for_scope(
            scope_ref="assistant",
            agent_id="assistant",
        )
        other_policy = service.effective_policy_for_scope(scope_ref="other")

        self.assertEqual(assistant_policy.max_recall_items, 2)
        self.assertFalse(assistant_policy.remember_enabled)
        self.assertEqual(other_policy.max_recall_items, 5)
        self.assertTrue(other_policy.remember_enabled)

    def test_disabled_policy_is_not_applied(self) -> None:
        service = MemoryPolicyService(_InMemoryMemoryPolicyRepository())
        service.upsert_policy(
            policy_id="assistant-disabled",
            target_kind="space",
            target_id="assistant",
            recall_enabled=False,
            remember_enabled=False,
            status="disabled",
        )

        policy = service.effective_policy_for_scope(scope_ref="assistant")

        self.assertTrue(policy.recall_enabled)
        self.assertTrue(policy.remember_enabled)

    def test_effective_policy_uses_deny_wins_and_min_cap(self) -> None:
        service = MemoryPolicyService(_InMemoryMemoryPolicyRepository())
        service.upsert_policy(
            policy_id="global-memory",
            target_kind="global",
            recall_enabled=True,
            remember_enabled=True,
            max_recall_items=8,
        )
        service.upsert_policy(
            policy_id="assistant-space",
            target_kind="space",
            target_id="assistant",
            recall_enabled=True,
            remember_enabled=False,
            max_recall_items=4,
        )
        service.upsert_policy(
            policy_id="assistant-agent",
            target_kind="agent",
            target_id="assistant",
            recall_enabled=True,
            remember_enabled=True,
            max_recall_items=2,
        )

        policy = service.effective_policy_for_scope(
            scope_ref="assistant",
            agent_id="assistant",
        )

        self.assertTrue(policy.recall_enabled)
        self.assertFalse(policy.remember_enabled)
        self.assertEqual(policy.max_recall_items, 2)

    def test_runtime_enforces_memory_policy(self) -> None:
        policy_service = MemoryPolicyService(_InMemoryMemoryPolicyRepository())
        policy_service.upsert_policy(
            policy_id="assistant-memory",
            target_kind="space",
            target_id="assistant",
            recall_enabled=True,
            remember_enabled=False,
            max_recall_items=2,
        )
        engine = _CapturingMemoryEngine()
        runtime = MemoryRuntimeService(
            scope_resolver=_StaticScopeResolver(
                MemoryUseContext(
                    space_id="assistant",
                    storage_root="/tmp/assistant",
                    retrieval_backend="hybrid",
                ),
            ),
            engine=engine,
            policy_provider=policy_service,
        )
        actor = MemoryActorContext(agent_id="assistant")

        runtime.recall(MemoryRecallRequest(actor=actor, query="x", max_items=9))

        assert engine.recall_request is not None
        self.assertEqual(engine.recall_request.max_items, 2)
        with self.assertRaisesRegex(ValueError, "remember is disabled"):
            runtime.remember(MemoryRememberRequest(actor=actor, content="hello"))


if __name__ == "__main__":
    unittest.main()
