from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from crxzipple.app.integration.memory_scope_resolution import AgentMemoryScopeResolver
from crxzipple.modules.agent.domain import (
    AgentLlmRoutingPolicy,
    AgentMemoryBinding,
    AgentNotFoundError,
    AgentProfile,
    AgentRuntimePreferences,
)
from crxzipple.modules.memory.application import MemorySpaceService
from crxzipple.modules.memory.domain import MemorySpace


class _InMemoryMemorySpaceRepository:
    def __init__(self) -> None:
        self.spaces: dict[str, MemorySpace] = {}

    def get(self, scope_ref: str) -> MemorySpace | None:
        return self.spaces.get(scope_ref)

    def list(self, *, include_disabled: bool = False) -> tuple[MemorySpace, ...]:
        values = self.spaces.values()
        if not include_disabled:
            values = [space for space in values if space.enabled]
        return tuple(sorted(values, key=lambda item: item.scope_ref))

    def upsert(self, space: MemorySpace) -> MemorySpace:
        self.spaces[space.scope_ref] = space
        return space

    def delete(self, scope_ref: str) -> None:
        self.spaces.pop(scope_ref, None)


class _AgentProfileReader:
    def __init__(self, *profiles: AgentProfile) -> None:
        self._profiles = {profile.id: profile for profile in profiles}

    def get_profile(self, profile_id: str) -> AgentProfile:
        try:
            return self._profiles[profile_id]
        except KeyError as exc:
            raise AgentNotFoundError(profile_id) from exc

    def list_profiles(self) -> list[AgentProfile]:
        return [self._profiles[key] for key in sorted(self._profiles)]


class MemorySpaceServiceTestCase(unittest.TestCase):
    def test_service_ensures_and_resolves_active_space(self) -> None:
        repository = _InMemoryMemorySpaceRepository()
        service = MemorySpaceService(repository)

        service.ensure_space(
            scope_ref="assistant",
            owner_kind="agent",
            owner_id="assistant",
            storage_root="/tmp/assistant",
            retrieval_backend="hybrid",
            replace_storage_root=True,
        )

        context = service.resolve_context("assistant")

        assert context is not None
        self.assertEqual(context.space_id, "assistant")
        self.assertEqual(context.storage_root, "/tmp/assistant")
        self.assertEqual(context.retrieval_backend, "hybrid")

    def test_agent_resolver_auto_creates_private_agent_space(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            storage_root = str(Path(tempdir) / "memory")
            profile = _agent_profile(
                "assistant",
                home_dir=str(Path(tempdir) / "assistant"),
                memory=AgentMemoryBinding(scope_ref="auto"),
            )
            service = MemorySpaceService(
                _InMemoryMemorySpaceRepository(),
                default_storage_root=storage_root,
            )
            resolver = AgentMemoryScopeResolver(
                agent_service=_AgentProfileReader(profile),  # type: ignore[arg-type]
                memory_spaces=service,
                default_retrieval_backend="hybrid",
            )

            context = resolver.resolve("assistant")

            assert context is not None
            self.assertEqual(context.space_id, "assistant")
            self.assertEqual(context.storage_root, service.storage_root_for_scope("assistant"))
            self.assertEqual(service.get_space("assistant").owner_kind, "agent")  # type: ignore[union-attr]

    def test_agent_resolver_does_not_require_agent_home_for_memory_storage(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            service = MemorySpaceService(
                _InMemoryMemorySpaceRepository(),
                default_storage_root=str(Path(tempdir) / "memory"),
            )
            profile = AgentProfile(
                id="assistant",
                name="assistant",
                llm_routing_policy=AgentLlmRoutingPolicy(default_llm_id="openai.test"),
                memory=AgentMemoryBinding(scope_ref="auto"),
            )
            resolver = AgentMemoryScopeResolver(
                agent_service=_AgentProfileReader(profile),  # type: ignore[arg-type]
                memory_spaces=service,
                default_retrieval_backend="hybrid",
            )

            context = resolver.resolve("assistant")

            assert context is not None
            self.assertEqual(context.storage_root, service.storage_root_for_scope("assistant"))
            self.assertEqual(profile.runtime_preferences.resolved_home_dir, None)

    def test_existing_disabled_space_is_not_reenabled_by_resolution(self) -> None:
        repository = _InMemoryMemorySpaceRepository()
        service = MemorySpaceService(repository)
        service.ensure_space(
            scope_ref="assistant",
            owner_kind="agent",
            owner_id="assistant",
            storage_root="/tmp/assistant",
            retrieval_backend="hybrid",
            replace_storage_root=True,
        )
        service.disable_space("assistant")

        service.ensure_space(
            scope_ref="assistant",
            owner_kind="agent",
            owner_id="assistant",
            storage_root="/tmp/assistant-updated",
            retrieval_backend="hybrid",
            replace_storage_root=True,
        )

        self.assertIsNone(service.resolve_context("assistant"))
        self.assertEqual(service.get_space("assistant").status, "disabled")  # type: ignore[union-attr]

    def test_shared_scope_reuses_memory_space_storage_root(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            first = _agent_profile(
                "assistant-a",
                home_dir=str(root / "a"),
                memory=AgentMemoryBinding(scope_ref="team-memory"),
            )
            second = _agent_profile(
                "assistant-b",
                home_dir=str(root / "b"),
                memory=AgentMemoryBinding(scope_ref="team-memory"),
            )
            service = MemorySpaceService(
                _InMemoryMemorySpaceRepository(),
                default_storage_root=str(root / "memory"),
            )
            resolver = AgentMemoryScopeResolver(
                agent_service=_AgentProfileReader(first, second),  # type: ignore[arg-type]
                memory_spaces=service,
                default_retrieval_backend="hybrid",
            )

            first_context = resolver.resolve("assistant-a")
            shared_context = resolver.resolve("team-memory")
            second_context = resolver.resolve("assistant-b")

            assert first_context is not None
            assert shared_context is not None
            assert second_context is not None
            self.assertEqual(first_context.space_id, "team-memory")
            self.assertEqual(shared_context.storage_root, first_context.storage_root)
            self.assertEqual(second_context.storage_root, first_context.storage_root)

    def test_resolver_classifies_project_team_and_system_scopes(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            service = MemorySpaceService(
                _InMemoryMemorySpaceRepository(),
                default_storage_root=str(Path(tempdir) / "memory"),
            )
            project = _agent_profile(
                "project-agent",
                home_dir=str(Path(tempdir) / "project-agent"),
                memory=AgentMemoryBinding(scope_ref="project:alpha"),
            )
            team = _agent_profile(
                "team-agent",
                home_dir=str(Path(tempdir) / "team-agent"),
                memory=AgentMemoryBinding(scope_ref="team:runtime"),
            )
            system = _agent_profile(
                "system-agent",
                home_dir=str(Path(tempdir) / "system-agent"),
                memory=AgentMemoryBinding(scope_ref="system:global"),
            )
            resolver = AgentMemoryScopeResolver(
                agent_service=_AgentProfileReader(project, team, system),  # type: ignore[arg-type]
                memory_spaces=service,
                default_retrieval_backend="hybrid",
            )

            self.assertIsNotNone(resolver.resolve("project-agent"))
            self.assertIsNotNone(resolver.resolve("team-agent"))
            self.assertIsNotNone(resolver.resolve("system-agent"))

            self.assertEqual(service.get_space("project:alpha").owner_kind, "project")  # type: ignore[union-attr]
            self.assertEqual(service.get_space("team:runtime").owner_kind, "team")  # type: ignore[union-attr]
            self.assertEqual(service.get_space("system:global").owner_kind, "system")  # type: ignore[union-attr]


def _agent_profile(
    profile_id: str,
    *,
    home_dir: str,
    memory: AgentMemoryBinding,
) -> AgentProfile:
    return AgentProfile(
        id=profile_id,
        name=profile_id,
        llm_routing_policy=AgentLlmRoutingPolicy(default_llm_id="openai.test"),
        runtime_preferences=AgentRuntimePreferences(
            home_dir=home_dir,
        ),
        memory=memory,
    )


if __name__ == "__main__":
    unittest.main()
