from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from crxzipple.app.integration import MemoryLegacyMigrationService
from crxzipple.modules.agent.application import UpdateAgentProfileInput
from crxzipple.modules.agent.domain import (
    AgentLlmRoutingPolicy,
    AgentMemoryBinding,
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
            values = [item for item in values if item.enabled]
        return tuple(sorted(values, key=lambda item: item.scope_ref))

    def upsert(self, space: MemorySpace) -> MemorySpace:
        self.spaces[space.scope_ref] = space
        return space

    def delete(self, scope_ref: str) -> None:
        self.spaces.pop(scope_ref, None)


class _AgentService:
    def __init__(self, *profiles: AgentProfile) -> None:
        self.profiles = {profile.id: profile for profile in profiles}
        self.updates: list[UpdateAgentProfileInput] = []

    def list_profiles(self) -> list[AgentProfile]:
        return [self.profiles[key] for key in sorted(self.profiles)]

    def update_profile(self, data: UpdateAgentProfileInput) -> AgentProfile:
        self.updates.append(data)
        profile = self.profiles[data.id]
        if isinstance(data.memory, AgentMemoryBinding):
            profile.apply_updates(memory=data.memory)
        self.profiles[data.id] = profile
        return profile


class MemoryLegacyMigrationServiceTestCase(unittest.TestCase):
    def test_migration_imports_sidecar_and_copies_legacy_memory_files(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            home_dir = root / "agent-home"
            (home_dir / ".state").mkdir(parents=True)
            (home_dir / ".state" / "memory-binding.json").write_text(
                json.dumps(
                    {
                        "scope_ref": "team:runtime",
                        "access": "read",
                    },
                ),
                encoding="utf-8",
            )
            (home_dir / "MEMORY.md").write_text("legacy long term", encoding="utf-8")
            (home_dir / "memory").mkdir()
            (home_dir / "memory" / "daily.md").write_text("daily note", encoding="utf-8")
            agent_service = _AgentService(_agent_profile("assistant", home_dir=home_dir))
            spaces = MemorySpaceService(
                _InMemoryMemorySpaceRepository(),
                default_storage_root=str(root / "memory-owner"),
            )
            service = MemoryLegacyMigrationService(
                agent_service=agent_service,
                memory_spaces=spaces,
                default_retrieval_backend="hybrid",
            )

            report = service.migrate_agent_homes(delete_sidecar=True)

            self.assertFalse((home_dir / ".state" / "memory-binding.json").exists())
            self.assertEqual(report.scanned, 1)
            self.assertEqual(report.updated_profiles, 1)
            self.assertEqual(report.created_spaces, 1)
            agent_report = report.agents[0]
            self.assertEqual(agent_report.scope_ref, "team:runtime")
            self.assertTrue(agent_report.sidecar_imported)
            self.assertTrue(agent_report.sidecar_deleted)
            self.assertEqual(agent_service.profiles["assistant"].memory.scope_ref, "team:runtime")
            self.assertEqual(agent_service.profiles["assistant"].memory.access, "read")
            space = spaces.get_space("team:runtime")
            assert space is not None
            self.assertEqual(space.owner_kind, "team")
            self.assertEqual(space.retrieval_backend, "hybrid")
            storage_root = Path(space.storage_root)
            self.assertEqual((storage_root / "MEMORY.md").read_text(encoding="utf-8"), "legacy long term")
            self.assertEqual((storage_root / "memory" / "daily.md").read_text(encoding="utf-8"), "daily note")

    def test_dry_run_reports_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            home_dir = root / "agent-home"
            (home_dir / ".state").mkdir(parents=True)
            (home_dir / ".state" / "memory-binding.json").write_text(
                '{"scope_ref":"shared-memory"}',
                encoding="utf-8",
            )
            (home_dir / "MEMORY.md").write_text("legacy", encoding="utf-8")
            agent_service = _AgentService(_agent_profile("assistant", home_dir=home_dir))
            spaces = MemorySpaceService(
                _InMemoryMemorySpaceRepository(),
                default_storage_root=str(root / "memory-owner"),
            )
            service = MemoryLegacyMigrationService(
                agent_service=agent_service,
                memory_spaces=spaces,
                default_retrieval_backend="hybrid",
            )

            report = service.migrate_agent_homes(dry_run=True, delete_sidecar=True)

            self.assertTrue(report.dry_run)
            self.assertEqual(report.updated_profiles, 1)
            self.assertEqual(report.created_spaces, 1)
            self.assertEqual(agent_service.updates, [])
            self.assertIsNone(spaces.get_space("shared-memory"))
            self.assertTrue((home_dir / ".state" / "memory-binding.json").exists())
            self.assertFalse((root / "memory-owner" / "shared-memory" / "MEMORY.md").exists())


def _agent_profile(profile_id: str, *, home_dir: Path) -> AgentProfile:
    return AgentProfile(
        id=profile_id,
        name=profile_id,
        llm_routing_policy=AgentLlmRoutingPolicy(default_llm_id="openai.test"),
        runtime_preferences=AgentRuntimePreferences(home_dir=str(home_dir)),
    )


if __name__ == "__main__":
    unittest.main()
