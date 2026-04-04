from __future__ import annotations

from tests.unit.cli_test_support import *


class SkillsCliTestCase(CliModuleTestCase):
    def test_skills_cli_lists_shows_validates_and_installs_packages(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace = root / "workspace"
            workspace.mkdir()
            source_skill = root / "release-ops-src"
            _write_skill_package(
                source_skill,
                name="release-ops",
                description="Prepare and validate releases.",
                instructions="# Release Ops\n\nFollow the release checklist.\n",
                version="1.2.0",
                tags=("release", "ops"),
                required_tools=("memory_search",),
                allowed_tools=("memory_search", "memory_read"),
            )

            list_result = self.runner.invoke(app, ["skills", "list"], env=self.env)
            self.assertEqual(list_result.exit_code, 0)
            self.assertIn('"name": "memory-recall"', list_result.stdout)

            show_result = self.runner.invoke(
                app,
                ["skills", "show", "memory-recall", "--include-instructions"],
                env=self.env,
            )
            self.assertEqual(show_result.exit_code, 0)
            self.assertIn('"instructions": "# Memory Recall', show_result.stdout)

            validate_result = self.runner.invoke(
                app,
                ["skills", "validate", str(source_skill)],
                env=self.env,
            )
            self.assertEqual(validate_result.exit_code, 0)
            self.assertIn('"name": "release-ops"', validate_result.stdout)
            self.assertIn('"version": "1.2.0"', validate_result.stdout)

            install_result = self.runner.invoke(
                app,
                [
                    "skills",
                    "install",
                    str(source_skill),
                    "--scope",
                    "workspace",
                    "--workspace-dir",
                    str(workspace),
                ],
                env=self.env,
            )
            self.assertEqual(install_result.exit_code, 0)
            self.assertIn('"scope": "workspace"', install_result.stdout)
            self.assertTrue(
                (workspace / ".crxzipple" / "skills" / "release-ops" / "skill.yaml").is_file(),
            )
            self.assertTrue(
                (workspace / ".crxzipple" / "skills" / "release-ops" / "SKILL.md").is_file(),
            )

            workspace_list_result = self.runner.invoke(
                app,
                ["skills", "list", "--workspace-dir", str(workspace)],
                env=self.env,
            )
            self.assertEqual(workspace_list_result.exit_code, 0)
            self.assertIn('"name": "release-ops"', workspace_list_result.stdout)


if __name__ == "__main__":
    unittest.main()
