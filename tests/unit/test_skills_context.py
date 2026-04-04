from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from crxzipple.modules.skills.application import SkillManager
from crxzipple.modules.skills.infrastructure.filesystem import (
    FilesystemSkillRepository,
)
from crxzipple.modules.skills.domain import SkillValidationError
from tests.unit.skill_test_support import write_skill_package as _write_skill_package


class SkillsContextTestCase(unittest.TestCase):
    def test_manager_builds_prompt_catalog_from_available_skills(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace = root / "workspace"
            workspace.mkdir()
            _write_skill_package(
                workspace / ".crxzipple" / "skills" / "repo-review",
                name="repo-review",
                description="Review repository changes carefully.",
                instructions="# Repo Review\n\nReview repository changes carefully.\n",
                version="1.2.3",
                tags=("review",),
                allowed_tools=("git_status", "git_diff"),
            )
            manager = SkillManager(
                repository=FilesystemSkillRepository(
                    global_root=root / "global",
                    system_root=root / "system",
                ),
            )

            catalog = manager.build_prompt_catalog(
                workspace_dir=str(workspace),
                surface="interactive",
            )

            self.assertIsNotNone(catalog)
            assert catalog is not None
            self.assertIn("# Available Skills", catalog.content)
            self.assertIn("repo-review", catalog.content)
            self.assertEqual(catalog.metadata["count"], 1)
            self.assertEqual(catalog.metadata["skills"][0]["name"], "repo-review")
            self.assertEqual(
                catalog.metadata["skills"][0]["allowed_tools"],
                ["git_status", "git_diff"],
            )

    def test_repository_returns_empty_when_no_roots_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            missing = Path(tempdir) / "missing"
            repository = FilesystemSkillRepository(
                global_root=missing,
                system_root=missing,
            )

            self.assertEqual(
                repository.list_available(workspace_dir=None),
                (),
            )

    def test_repository_discovers_workspace_global_and_system_skills(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace = root / "workspace"
            global_root = root / "global"
            system_root = root / "system"
            _write_skill_package(
                workspace / ".crxzipple" / "skills" / "repo-review",
                name="repo-review",
                description="Review repository changes carefully.",
                instructions="# Repo Review\n\nReview repository changes carefully.\n",
            )
            _write_skill_package(
                global_root / "daily-brief",
                name="daily-brief",
                description="Summarize the day in one concise brief.",
                instructions="# Daily Brief\n\nSummarize the day.\n",
            )
            _write_skill_package(
                system_root / "openai-docs",
                name="openai-docs",
                description="Use official OpenAI documentation for current answers.",
                instructions="# OpenAI Docs\n\nUse official docs.\n",
            )
            repository = FilesystemSkillRepository(
                global_root=global_root,
                system_root=system_root,
            )

            skills = repository.list_available(workspace_dir=str(workspace))

            self.assertEqual(
                [skill.name for skill in skills],
                ["daily-brief", "openai-docs", "repo-review"],
            )
            self.assertEqual(
                [skill.source for skill in skills],
                ["global", "system", "workspace"],
            )
            self.assertEqual(
                skills[2].instructions_path,
                str(
                    (workspace / ".crxzipple" / "skills" / "repo-review" / "SKILL.md").resolve(),
                ),
            )

    def test_repository_parses_manifest_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            system_root = root / "system"
            _write_skill_package(
                system_root / "memory-recall",
                name="memory-recall",
                description="Recall durable memory before answering.",
                version="1",
                tags=("memory", "recall"),
                required_tools=("memory_search",),
                allowed_tools=("memory_search", "memory_read", "memory_write_daily"),
                instructions="# Memory Recall\n\nUse durable memory.\n",
            )
            repository = FilesystemSkillRepository(
                global_root=root / "global",
                system_root=system_root,
            )

            skills = repository.list_available(workspace_dir=None)

            self.assertEqual(len(skills), 1)
            self.assertEqual(skills[0].name, "memory-recall")
            self.assertEqual(
                skills[0].description,
                "Recall durable memory before answering.",
            )
            self.assertEqual(skills[0].version, "1")
            self.assertEqual(skills[0].tags, ("memory", "recall"))
            self.assertEqual(skills[0].required_tools, ("memory_search",))
            self.assertEqual(
                skills[0].allowed_tools,
                ("memory_search", "memory_read", "memory_write_daily"),
            )

    def test_repository_prefers_workspace_over_global_and_system(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace = root / "workspace"
            global_root = root / "global"
            system_root = root / "system"
            _write_skill_package(
                workspace / ".crxzipple" / "skills" / "repo-review",
                name="repo-review",
                description="Workspace-local review instructions.",
                instructions="# Repo Review\n\nWorkspace-local review instructions.\n",
            )
            _write_skill_package(
                global_root / "repo-review",
                name="repo-review",
                description="Global review instructions.",
                instructions="# Repo Review\n\nGlobal review instructions.\n",
            )
            _write_skill_package(
                system_root / "repo-review",
                name="repo-review",
                description="System review instructions.",
                instructions="# Repo Review\n\nSystem review instructions.\n",
            )
            repository = FilesystemSkillRepository(
                global_root=global_root,
                system_root=system_root,
            )

            skills = repository.list_available(workspace_dir=str(workspace))

            self.assertEqual(len(skills), 1)
            self.assertEqual(skills[0].name, "repo-review")
            self.assertEqual(skills[0].source, "workspace")
            self.assertIn("workspace", skills[0].description.lower())

    def test_repository_ignores_directories_without_valid_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            system_root = root / "system"
            invalid = system_root / "broken-skill"
            invalid.mkdir(parents=True)
            (invalid / "SKILL.md").write_text("# Broken\n", encoding="utf-8")
            repository = FilesystemSkillRepository(
                global_root=root / "global",
                system_root=system_root,
            )

            self.assertEqual(repository.list_available(workspace_dir=None), ())

    def test_read_loads_skill_instructions_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            system_root = root / "system"
            _write_skill_package(
                system_root / "release-ops",
                name="release-ops",
                description="Prepare and validate releases.",
                instructions="# Release Ops\n\nFollow the release checklist.\n",
            )
            repository = FilesystemSkillRepository(
                global_root=root / "global",
                system_root=system_root,
            )

            loaded = repository.read(
                workspace_dir=None,
                skill_name="release-ops",
                path=None,
            )

            self.assertEqual(loaded.package.name, "release-ops")
            self.assertEqual(loaded.requested_path, "SKILL.md")
            self.assertIn("release checklist", loaded.content)

    def test_read_can_load_nested_skill_resource_within_package_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            system_root = root / "system"
            skill_root = system_root / "release-ops"
            _write_skill_package(
                skill_root,
                name="release-ops",
                description="Prepare and validate releases.",
                instructions=(
                    "# Release Ops\n\n"
                    "If you need the detailed checklist, read references/checklist.md.\n"
                ),
            )
            references_root = skill_root / "references"
            references_root.mkdir()
            (references_root / "checklist.md").write_text(
                "# Checklist\n\n- Cut branch\n- Run smoke tests\n",
                encoding="utf-8",
            )
            repository = FilesystemSkillRepository(
                global_root=root / "global",
                system_root=system_root,
            )

            loaded = repository.read(
                workspace_dir=None,
                skill_name="release-ops",
                path="references/checklist.md",
            )

            self.assertEqual(loaded.requested_path, "references/checklist.md")
            self.assertTrue(loaded.resolved_path.endswith("references/checklist.md"))
            self.assertIn("Cut branch", loaded.content)

    def test_read_rejects_paths_that_escape_the_skill_package(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            system_root = root / "system"
            skill_root = system_root / "release-ops"
            _write_skill_package(
                skill_root,
                name="release-ops",
                description="Prepare and validate releases.",
                instructions="# Release Ops\n\nFollow the release checklist.\n",
            )
            outside_file = system_root / "outside.md"
            outside_file.write_text("should stay unreadable\n", encoding="utf-8")
            repository = FilesystemSkillRepository(
                global_root=root / "global",
                system_root=system_root,
            )

            with self.assertRaises(SkillValidationError):
                repository.read(
                    workspace_dir=None,
                    skill_name="release-ops",
                    path="../outside.md",
                )
