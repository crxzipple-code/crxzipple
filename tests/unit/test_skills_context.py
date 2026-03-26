from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from crxzipple.modules.orchestration.application.skills_context import (
    load_available_skills,
)


class SkillsContextTestCase(unittest.TestCase):
    def test_load_available_skills_returns_empty_when_no_roots_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            missing = Path(tempdir) / "missing"
            self.assertEqual(
                load_available_skills(
                    None,
                    global_root=missing,
                    system_root=missing,
                ),
                (),
            )

    def test_load_available_skills_discovers_workspace_global_and_system_skills(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace = root / "workspace"
            global_root = root / "global"
            system_root = root / "system"
            (workspace / ".crxzipple" / "skills" / "repo-review").mkdir(
                parents=True,
            )
            (global_root / "daily-brief").mkdir(parents=True)
            (system_root / "openai-docs").mkdir(parents=True)
            (workspace / ".crxzipple" / "skills" / "repo-review" / "SKILL.md").write_text(
                "# Repo Review\n\nUse this skill when reviewing repository changes.\n",
                encoding="utf-8",
            )
            (global_root / "daily-brief" / "SKILL.md").write_text(
                "Summarize the day in one concise brief.\n",
                encoding="utf-8",
            )
            (system_root / "openai-docs" / "SKILL.md").write_text(
                "# OpenAI Docs\n\nUse official OpenAI documentation for current answers.\n",
                encoding="utf-8",
            )

            skills = load_available_skills(
                str(workspace),
                global_root=global_root,
                system_root=system_root,
            )

            self.assertEqual(
                [skill.name for skill in skills],
                ["daily-brief", "openai-docs", "repo-review"],
            )
            self.assertEqual(
                [skill.source for skill in skills],
                ["global", "system", "workspace"],
            )
            self.assertIn("repository changes", skills[2].description)

    def test_load_available_skills_prefers_workspace_over_global_and_system(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace = root / "workspace"
            global_root = root / "global"
            system_root = root / "system"
            (workspace / ".crxzipple" / "skills" / "repo-review").mkdir(
                parents=True,
            )
            (global_root / "repo-review").mkdir(parents=True)
            (system_root / "repo-review").mkdir(parents=True)
            (workspace / ".crxzipple" / "skills" / "repo-review" / "SKILL.md").write_text(
                "Workspace-local review instructions.\n",
                encoding="utf-8",
            )
            (global_root / "repo-review" / "SKILL.md").write_text(
                "Global review instructions.\n",
                encoding="utf-8",
            )
            (system_root / "repo-review" / "SKILL.md").write_text(
                "System review instructions.\n",
                encoding="utf-8",
            )

            skills = load_available_skills(
                str(workspace),
                global_root=global_root,
                system_root=system_root,
            )

            self.assertEqual(len(skills), 1)
            self.assertEqual(skills[0].name, "repo-review")
            self.assertEqual(skills[0].source, "workspace")
            self.assertIn("Workspace-local", skills[0].description)

    def test_load_available_skills_ignores_directories_without_skill_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            system_root = root / "system"
            (system_root / "missing-skill").mkdir(parents=True)

            skills = load_available_skills(
                None,
                global_root=root / "global",
                system_root=system_root,
            )

            self.assertEqual(skills, ())
