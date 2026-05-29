from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
import unittest

from crxzipple.modules.memory import (
    FileBackedMemoryService,
    MEMORY_REMEMBER_SUCCEEDED_EVENT,
    MemoryActorContext,
    MemoryPolicyService,
    MemoryRecallRequest,
    MemoryRememberRequest,
    MemoryRuntimeService,
    MemoryUseContext,
)
from crxzipple.modules.memory.domain import MemorySpace
from crxzipple.modules.memory.domain import MemoryPolicy
from crxzipple.modules.memory.infrastructure import (
    FileMarkdownMemoryEngine,
    FileMemoryIndexManager,
    FileMemoryStore,
)


@dataclass(frozen=True, slots=True)
class _StaticScopeResolver:
    context: MemoryUseContext

    def resolve(self, space_ref: str | None) -> MemoryUseContext | None:
        if space_ref == self.context.space_id:
            return self.context
        return None


@dataclass(frozen=True, slots=True)
class _MappingScopeResolver:
    contexts: dict[str, MemoryUseContext]

    def resolve(self, space_ref: str | None) -> MemoryUseContext | None:
        if space_ref is None:
            return None
        return self.contexts.get(space_ref)


@dataclass(frozen=True, slots=True)
class _MappingSpaceInventory:
    spaces: dict[str, MemorySpace]

    def get_space(self, scope_ref: str) -> MemorySpace | None:
        return self.spaces.get(scope_ref)

    def list_spaces(self, *, include_disabled: bool = False) -> tuple[MemorySpace, ...]:
        values = self.spaces.values()
        if not include_disabled:
            values = [space for space in values if space.enabled]
        return tuple(sorted(values, key=lambda item: item.scope_ref))


class _MemoryPolicyRepository:
    def __init__(self) -> None:
        self.policies: dict[str, MemoryPolicy] = {}

    def get(self, policy_id: str) -> MemoryPolicy | None:
        return self.policies.get(policy_id)

    def list(self, *, include_disabled: bool = False) -> tuple[MemoryPolicy, ...]:
        values = self.policies.values()
        if not include_disabled:
            values = [policy for policy in values if policy.enabled]
        return tuple(values)

    def upsert(self, policy: MemoryPolicy) -> MemoryPolicy:
        self.policies[policy.policy_id] = policy
        return policy

    def delete(self, policy_id: str) -> None:
        self.policies.pop(policy_id, None)


class MemoryRuntimeServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.context = MemoryUseContext(
            space_id="assistant",
            storage_root=str(self.root),
            retrieval_backend="hybrid",
        )
        self.events: list[tuple[str, dict[str, object]]] = []
        file_service = FileBackedMemoryService(
            store=FileMemoryStore(),
            index_manager=FileMemoryIndexManager(),
            event_emitter=lambda name, payload: self.events.append((name, payload)),
        )
        self.runtime = MemoryRuntimeService(
            scope_resolver=_StaticScopeResolver(self.context),
            engine=FileMarkdownMemoryEngine(file_service),
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_remember_and_recall_use_resolved_agent_scope(self) -> None:
        actor = MemoryActorContext(agent_id="assistant")

        remembered = self.runtime.remember(
            MemoryRememberRequest(
                actor=actor,
                content="Remember that the runtime uses scoped memory engines.",
            ),
        )

        self.assertEqual(remembered.scope.context.space_id, "assistant")
        self.assertIsNotNone(remembered.write_result)
        assert remembered.write_result is not None
        self.assertTrue(remembered.write_result.path.startswith("memory/"))

        recalled = self.runtime.recall(
            MemoryRecallRequest(
                actor=actor,
                query="scoped memory engines",
                max_items=3,
            ),
        )

        self.assertEqual(recalled.scope.engine_id, "file_markdown")
        self.assertEqual(len(recalled.items), 1)
        self.assertEqual(recalled.hits[0].path, remembered.write_result.path)
        remembered_events = [
            event for event in self.events if event[0] == MEMORY_REMEMBER_SUCCEEDED_EVENT
        ]
        self.assertEqual(len(remembered_events), 1)
        self.assertEqual(remembered_events[0][1]["space_id"], "assistant")
        self.assertEqual(remembered_events[0][1]["path"], remembered.write_result.path)
        self.assertNotIn("memory.write.succeeded", [event[0] for event in self.events])

    def test_recall_can_read_cited_excerpt(self) -> None:
        actor = MemoryActorContext(agent_id="assistant")
        remembered = self.runtime.remember(
            MemoryRememberRequest(
                actor=actor,
                content="Cited memory can be read through recall.",
            ),
        )
        assert remembered.write_result is not None
        citation = (
            f"{remembered.write_result.path}:"
            f"{remembered.write_result.line_start}-{remembered.write_result.line_end}"
        )

        recalled = self.runtime.recall(
            MemoryRecallRequest(
                actor=actor,
                citation=citation,
            ),
        )

        self.assertIsNotNone(recalled.excerpt)
        assert recalled.excerpt is not None
        self.assertIn("Cited memory", recalled.excerpt.text)

    def test_missing_scope_fails_before_engine_call(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "requires agent_id or scope_ref",
        ):
            self.runtime.resolve_access_plan(MemoryActorContext())

    def test_actor_context_from_attrs_accepts_current_scope_keys_only(self) -> None:
        actor = MemoryActorContext.from_attrs(
            {
                "agent_id": "assistant",
                "scope_ref": "project:runtime",
                "memory_space_id": "legacy-space",
                "memory_space": "legacy-memory",
            },
        )
        legacy_only = MemoryActorContext.from_attrs(
            {
                "agent_id": "assistant",
                "memory_space_id": "legacy-space",
            },
        )

        self.assertEqual(actor.scope_ref, "project:runtime")
        self.assertIsNone(legacy_only.scope_ref)
        self.assertEqual(legacy_only.requested_scope_ref, "assistant")

    def test_child_sessions_for_same_agent_share_memory_scope(self) -> None:
        runtime = self._runtime_for_contexts(
            {
                "assistant": MemoryUseContext(
                    space_id="assistant",
                    storage_root=str(self.root / "assistant-memory"),
                    retrieval_backend="hybrid",
                ),
            },
        )

        runtime.remember(
            MemoryRememberRequest(
                actor=MemoryActorContext(
                    agent_id="assistant",
                    session_key="agent:assistant:child-a",
                    active_session_id="child-a",
                ),
                content="Child session memory is shared by agent scope.",
            ),
        )
        recalled = runtime.recall(
            MemoryRecallRequest(
                actor=MemoryActorContext(
                    agent_id="assistant",
                    session_key="agent:assistant:child-b",
                    active_session_id="child-b",
                ),
                query="shared by agent scope",
            ),
        )

        self.assertEqual(len(recalled.items), 1)
        self.assertEqual(recalled.scope.scope_ref, "assistant")

    def test_different_agents_have_isolated_default_memory_scopes(self) -> None:
        runtime = self._runtime_for_contexts(
            {
                "assistant-a": MemoryUseContext(
                    space_id="assistant-a",
                    storage_root=str(self.root / "assistant-a-memory"),
                    retrieval_backend="hybrid",
                ),
                "assistant-b": MemoryUseContext(
                    space_id="assistant-b",
                    storage_root=str(self.root / "assistant-b-memory"),
                    retrieval_backend="hybrid",
                ),
            },
        )

        runtime.remember(
            MemoryRememberRequest(
                actor=MemoryActorContext(agent_id="assistant-a"),
                content="Private launch code belongs only to assistant A.",
            ),
        )

        same_agent = runtime.recall(
            MemoryRecallRequest(
                actor=MemoryActorContext(agent_id="assistant-a"),
                query="private launch code",
            ),
        )
        other_agent = runtime.recall(
            MemoryRecallRequest(
                actor=MemoryActorContext(agent_id="assistant-b"),
                query="private launch code",
            ),
        )

        self.assertEqual(len(same_agent.items), 1)
        self.assertEqual(other_agent.items, ())

    def test_agents_can_recall_default_shared_memory_layer(self) -> None:
        runtime = self._runtime_for_contexts(
            {
                "assistant-a": MemoryUseContext(
                    space_id="assistant-a",
                    storage_root=str(self.root / "assistant-a-memory"),
                    retrieval_backend="hybrid",
                ),
                "assistant-b": MemoryUseContext(
                    space_id="assistant-b",
                    storage_root=str(self.root / "assistant-b-memory"),
                    retrieval_backend="hybrid",
                ),
                "team-memory": MemoryUseContext(
                    space_id="team-memory",
                    storage_root=str(self.root / "team-memory-memory"),
                    retrieval_backend="hybrid",
                ),
            },
            spaces={
                "assistant-a": self._space("assistant-a", "agent", "assistant-a"),
                "assistant-b": self._space("assistant-b", "agent", "assistant-b"),
                "team-memory": self._space(
                    "team-memory",
                    "shared",
                    "team",
                    metadata={"default_recall_enabled": True},
                ),
            },
        )

        runtime.remember(
            MemoryRememberRequest(
                actor=MemoryActorContext(scope_ref="team-memory"),
                content="Team memory can be recalled by explicitly bound agents.",
            ),
        )
        recalled = runtime.recall(
            MemoryRecallRequest(
                actor=MemoryActorContext(agent_id="assistant-b"),
                query="explicitly bound agents",
            ),
        )

        self.assertEqual(len(recalled.items), 1)
        self.assertEqual(recalled.scope.scope_ref, "assistant-b")
        self.assertEqual(recalled.items[0].source_scope_ref, "team-memory")
        self.assertEqual(recalled.items[0].source_layer_kind, "shared")

    def test_shared_memory_write_requires_writable_layer_gate(self) -> None:
        runtime = self._runtime_for_contexts(
            {
                "assistant": MemoryUseContext(
                    space_id="assistant",
                    storage_root=str(self.root / "assistant-memory"),
                    retrieval_backend="hybrid",
                ),
                "common": MemoryUseContext(
                    space_id="common",
                    storage_root=str(self.root / "common-memory"),
                    retrieval_backend="hybrid",
                ),
            },
            spaces={
                "assistant": self._space("assistant", "agent", "assistant"),
                "common": self._space(
                    "common",
                    "shared",
                    "common",
                    metadata={"default_recall_enabled": True},
                ),
            },
        )

        with self.assertRaisesRegex(ValueError, "not writable"):
            runtime.remember(
                MemoryRememberRequest(
                    actor=MemoryActorContext(agent_id="assistant"),
                    content="This should not enter common memory.",
                    target_scope_ref="common",
                ),
            )

        private_write = runtime.remember(
            MemoryRememberRequest(
                actor=MemoryActorContext(agent_id="assistant"),
                content="Default writes stay in private memory.",
            ),
        )

        self.assertEqual(private_write.scope.scope_ref, "assistant")

    def test_shared_memory_recall_policy_can_exclude_default_layer(self) -> None:
        policy_service = MemoryPolicyService(_MemoryPolicyRepository())
        policy_service.upsert_policy(
            policy_id="common-recall-off",
            target_kind="space",
            target_id="common",
            recall_enabled=False,
            remember_enabled=True,
        )
        runtime = self._runtime_for_contexts(
            {
                "assistant": MemoryUseContext(
                    space_id="assistant",
                    storage_root=str(self.root / "assistant-memory"),
                    retrieval_backend="hybrid",
                ),
                "common": MemoryUseContext(
                    space_id="common",
                    storage_root=str(self.root / "common-memory"),
                    retrieval_backend="hybrid",
                ),
            },
            spaces={
                "assistant": self._space("assistant", "agent", "assistant"),
                "common": self._space(
                    "common",
                    "shared",
                    "common",
                    metadata={"default_recall_enabled": True},
                ),
            },
            policy_provider=policy_service,
        )

        runtime.remember(
            MemoryRememberRequest(
                actor=MemoryActorContext(scope_ref="common"),
                content="Common recall disabled sample.",
            ),
        )
        recalled = runtime.recall(
            MemoryRecallRequest(
                actor=MemoryActorContext(agent_id="assistant"),
                query="Common recall disabled sample",
            ),
        )

        self.assertEqual(recalled.items, ())
        self.assertEqual(
            [layer.scope_ref for layer in recalled.searched_layers],
            ["assistant"],
        )

    def _runtime_for_contexts(
        self,
        contexts: dict[str, MemoryUseContext],
        *,
        spaces: dict[str, MemorySpace] | None = None,
        policy_provider: object | None = None,
    ) -> MemoryRuntimeService:
        file_service = FileBackedMemoryService(
            store=FileMemoryStore(),
            index_manager=FileMemoryIndexManager(),
        )
        return MemoryRuntimeService(
            scope_resolver=_MappingScopeResolver(contexts),
            engine=FileMarkdownMemoryEngine(file_service),
            space_inventory=(
                _MappingSpaceInventory(spaces)
                if spaces is not None
                else None
            ),
            policy_provider=policy_provider,  # type: ignore[arg-type]
        )

    def _space(
        self,
        scope_ref: str,
        owner_kind: str,
        owner_id: str,
        *,
        metadata: dict[str, object] | None = None,
    ) -> MemorySpace:
        context = MemoryUseContext(
            space_id=scope_ref,
            storage_root=str(self.root / f"{scope_ref}-memory"),
            retrieval_backend="hybrid",
        )
        return MemorySpace(
            scope_ref=scope_ref,
            owner_kind=owner_kind,  # type: ignore[arg-type]
            owner_id=owner_id,
            engine_id="file_markdown",
            storage_root=context.storage_root,
            retrieval_backend=context.retrieval_backend,
            metadata=metadata or {},
        )


if __name__ == "__main__":
    unittest.main()
