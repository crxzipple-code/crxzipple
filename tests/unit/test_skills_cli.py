from __future__ import annotations

from tests.unit.cli_test_support import *


class SkillsCliTestCase(CliModuleTestCase):
    def test_skills_cli_manages_authoring_draft_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = Path(tempdir) / "workspace"
            workspace.mkdir()

            create_result = self.runner.invoke(
                app,
                [
                    "skills",
                    "draft",
                    "create",
                    "postmortem-writing",
                    "--description",
                    "Capture incident learning as reusable guidance.",
                    "--instructions",
                    "# Postmortem Writing\n\nSummarize facts and follow-ups.",
                    "--workspace-dir",
                    str(workspace),
                    "--required-tools",
                    "workspace_read",
                    "--support-file",
                    "references/checklist.md=# Checklist",
                    "--actor",
                    "cli-test",
                    "--reason",
                    "capture reusable practice",
                ],
                env=self.env,
            )
            self.assertEqual(create_result.exit_code, 0)
            draft = json.loads(create_result.stdout)
            draft_id = draft["draft_id"]
            self.assertEqual(draft["status"], "draft")
            self.assertEqual(draft["skill_name"], "postmortem-writing")
            self.assertEqual(
                draft["requirements"]["required_tools"],
                ["workspace_read"],
            )
            self.assertEqual(
                draft["support_files"][0]["path"],
                "references/checklist.md",
            )

            list_result = self.runner.invoke(
                app,
                [
                    "skills",
                    "draft",
                    "list",
                    "--skill-name",
                    "postmortem-writing",
                    "--workspace-dir",
                    str(workspace),
                ],
                env=self.env,
            )
            self.assertEqual(list_result.exit_code, 0)
            self.assertEqual(
                [item["draft_id"] for item in json.loads(list_result.stdout)],
                [draft_id],
            )

            show_result = self.runner.invoke(
                app,
                ["skills", "draft", "show", draft_id],
                env=self.env,
            )
            self.assertEqual(show_result.exit_code, 0)
            self.assertIn("Postmortem Writing", show_result.stdout)

            update_result = self.runner.invoke(
                app,
                [
                    "skills",
                    "draft",
                    "update",
                    draft_id,
                    "--instructions",
                    "# Postmortem Writing\n\nStart from timeline, impact, and owners.",
                    "--requirements-json",
                    json.dumps({"suggested_tools": ["workspace_search"]}),
                ],
                env=self.env,
            )
            self.assertEqual(update_result.exit_code, 0)
            updated = json.loads(update_result.stdout)
            self.assertEqual(
                updated["requirements"]["suggested_tools"],
                ["workspace_search"],
            )

            validate_result = self.runner.invoke(
                app,
                ["skills", "draft", "validate", draft_id],
                env=self.env,
            )
            self.assertEqual(validate_result.exit_code, 0)
            validated = json.loads(validate_result.stdout)
            self.assertEqual(validated["status"], "validated")
            self.assertTrue(validated["validation"]["valid"])

            diff_result = self.runner.invoke(
                app,
                ["skills", "draft", "diff", draft_id],
                env=self.env,
            )
            self.assertEqual(diff_result.exit_code, 0)
            diffed = json.loads(diff_result.stdout)
            self.assertIn(
                "Create skill 'postmortem-writing'",
                diffed["diff"]["summary"],
            )

            reject_result = self.runner.invoke(
                app,
                [
                    "skills",
                    "draft",
                    "reject",
                    draft_id,
                    "--reason",
                    "superseded by another draft",
                ],
                env=self.env,
            )
            self.assertEqual(reject_result.exit_code, 0)
            self.assertEqual(json.loads(reject_result.stdout)["status"], "rejected")

            delete_result = self.runner.invoke(
                app,
                ["skills", "draft", "delete", draft_id],
                env=self.env,
            )
            self.assertEqual(delete_result.exit_code, 0)
            self.assertEqual(json.loads(delete_result.stdout)["draft_id"], draft_id)

            audit_result = self.runner.invoke(
                app,
                ["skills", "draft", "audit", draft_id],
                env=self.env,
            )
            self.assertEqual(audit_result.exit_code, 0)
            self.assertEqual(
                [item["action"] for item in reversed(json.loads(audit_result.stdout))],
                ["create", "update", "validate", "diff", "reject", "delete"],
            )

            apply_create_result = self.runner.invoke(
                app,
                [
                    "skills",
                    "draft",
                    "create",
                    "release-notes",
                    "--description",
                    "Prepare release notes from completed work.",
                    "--instructions",
                    "# Release Notes\n\nGroup changes by user-visible outcome.",
                    "--workspace-dir",
                    str(workspace),
                ],
                env=self.env,
            )
            self.assertEqual(apply_create_result.exit_code, 0)
            apply_draft_id = json.loads(apply_create_result.stdout)["draft_id"]

            apply_result = self.runner.invoke(
                app,
                [
                    "skills",
                    "draft",
                    "apply",
                    apply_draft_id,
                    "--reason",
                    "approved by cli test",
                ],
                env=self.env,
            )
            self.assertEqual(apply_result.exit_code, 0)
            self.assertEqual(json.loads(apply_result.stdout)["status"], "applied")
            self.assertTrue(
                (
                    workspace
                    / ".crxzipple"
                    / "skills"
                    / "release-notes"
                    / "SKILL.md"
                ).is_file(),
            )

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
            external_root = root / "external-skills"
            _write_skill_package(
                external_root / "incident-response",
                name="incident-response",
                description="Coordinate incident response.",
                instructions="# Incident Response\n\nTriage production incidents.",
                tags=("incident",),
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

            get_result = self.runner.invoke(
                app,
                ["skills", "get", "memory-recall"],
                env=self.env,
            )
            self.assertEqual(get_result.exit_code, 0)
            self.assertIn('"name": "memory-recall"', get_result.stdout)

            read_result = self.runner.invoke(
                app,
                ["skills", "read", "memory-recall"],
                env=self.env,
            )
            self.assertEqual(read_result.exit_code, 0)
            self.assertIn('"requested_path": "SKILL.md"', read_result.stdout)
            self.assertIn('"content": "# Memory Recall', read_result.stdout)

            create_result = self.runner.invoke(
                app,
                [
                    "skills",
                    "create",
                    "analysis-skill",
                    "--description",
                    "Analyze local project context.",
                    "--instructions",
                    "# Analysis Skill",
                    "--workspace-dir",
                    str(workspace),
                    "--tags",
                    "analysis",
                    "--required-tools",
                    "workspace_read",
                ],
                env=self.env,
            )
            self.assertEqual(create_result.exit_code, 0)
            self.assertIn('"action": "create"', create_result.stdout)

            update_result = self.runner.invoke(
                app,
                [
                    "skills",
                    "update",
                    "analysis-skill",
                    "--workspace-dir",
                    str(workspace),
                    "--description",
                    "Analyze workspace context.",
                    "--suggested-tools",
                    "workspace_read,workspace_search",
                ],
                env=self.env,
            )
            self.assertEqual(update_result.exit_code, 0)
            self.assertIn("Analyze workspace context.", update_result.stdout)

            write_instructions_result = self.runner.invoke(
                app,
                [
                    "skills",
                    "write-instructions",
                    "analysis-skill",
                    "# Analysis Skill\n\nPrefer evidence.",
                    "--workspace-dir",
                    str(workspace),
                ],
                env=self.env,
            )
            self.assertEqual(write_instructions_result.exit_code, 0)
            self.assertIn('"action": "write_instructions"', write_instructions_result.stdout)

            write_file_result = self.runner.invoke(
                app,
                [
                    "skills",
                    "write-file",
                    "analysis-skill",
                    "references/guide.md",
                    "# Guide",
                    "--workspace-dir",
                    str(workspace),
                ],
                env=self.env,
            )
            self.assertEqual(write_file_result.exit_code, 0)
            self.assertIn('"action": "write_file"', write_file_result.stdout)

            delete_file_result = self.runner.invoke(
                app,
                [
                    "skills",
                    "delete-file",
                    "analysis-skill",
                    "references/guide.md",
                    "--workspace-dir",
                    str(workspace),
                ],
                env=self.env,
            )
            self.assertEqual(delete_file_result.exit_code, 0)
            self.assertIn('"action": "delete_file"', delete_file_result.stdout)

            delete_created_result = self.runner.invoke(
                app,
                [
                    "skills",
                    "delete",
                    "analysis-skill",
                    "--workspace-dir",
                    str(workspace),
                ],
                env=self.env,
            )
            self.assertEqual(delete_created_result.exit_code, 0)

            validate_result = self.runner.invoke(
                app,
                ["skills", "validate", str(source_skill)],
                env=self.env,
            )
            self.assertEqual(validate_result.exit_code, 0)
            self.assertIn('"name": "release-ops"', validate_result.stdout)
            self.assertIn('"version": "1.2.0"', validate_result.stdout)
            self.assertIn('"requirements"', validate_result.stdout)
            self.assertIn('"suggested_tools": [', validate_result.stdout)
            self.assertNotIn('"allowed_tools"', validate_result.stdout)

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
            self.assertFalse(
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

            source_result = self.runner.invoke(
                app,
                ["skills", "source", "list", "--workspace-dir", str(workspace)],
                env=self.env,
            )
            self.assertEqual(source_result.exit_code, 0)
            self.assertIn('"source_id": "workspace"', source_result.stdout)

            create_source_result = self.runner.invoke(
                app,
                [
                    "skills",
                    "source",
                    "create",
                    "external-local",
                    str(external_root),
                ],
                env=self.env,
            )
            self.assertEqual(create_source_result.exit_code, 0)
            self.assertIn('"action": "create"', create_source_result.stdout)
            self.assertIn('"package_count": 1', create_source_result.stdout)

            external_list_result = self.runner.invoke(
                app,
                ["skills", "list", "--source", "external-local"],
                env=self.env,
            )
            self.assertEqual(external_list_result.exit_code, 0)
            self.assertIn('"name": "incident-response"', external_list_result.stdout)

            external_sync_result = self.runner.invoke(
                app,
                ["skills", "sync", "--source-id", "external-local"],
                env=self.env,
            )
            self.assertEqual(external_sync_result.exit_code, 0)
            self.assertIn('"name": "incident-response"', external_sync_result.stdout)

            delete_source_result = self.runner.invoke(
                app,
                ["skills", "source", "delete", "external-local"],
                env=self.env,
            )
            self.assertEqual(delete_source_result.exit_code, 0)
            self.assertIn('"action": "delete"', delete_source_result.stdout)

            sync_result = self.runner.invoke(
                app,
                [
                    "skills",
                    "sync",
                    "--workspace-dir",
                    str(workspace),
                    "--source-id",
                    "workspace",
                ],
                env=self.env,
            )
            self.assertEqual(sync_result.exit_code, 0)
            self.assertIn('"synced_count": 1', sync_result.stdout)

            readiness_result = self.runner.invoke(
                app,
                [
                    "skills",
                    "readiness",
                    "release-ops",
                    "--workspace-dir",
                    str(workspace),
                ],
                env=self.env,
            )
            self.assertEqual(readiness_result.exit_code, 0)
            self.assertIn('"status": "ready"', readiness_result.stdout)

            disable_result = self.runner.invoke(
                app,
                [
                    "skills",
                    "disable",
                    "release-ops",
                    "--workspace-dir",
                    str(workspace),
                    "--reason",
                    "test",
                ],
                env=self.env,
            )
            self.assertEqual(disable_result.exit_code, 0)
            self.assertIn('"action": "disable"', disable_result.stdout)

            hidden_result = self.runner.invoke(
                app,
                ["skills", "list", "--workspace-dir", str(workspace)],
                env=self.env,
            )
            self.assertEqual(hidden_result.exit_code, 0)
            self.assertNotIn('"name": "release-ops"', hidden_result.stdout)

            enable_result = self.runner.invoke(
                app,
                [
                    "skills",
                    "enable",
                    "release-ops",
                    "--workspace-dir",
                    str(workspace),
                    "--reason",
                    "test",
                ],
                env=self.env,
            )
            self.assertEqual(enable_result.exit_code, 0)
            self.assertIn('"action": "enable"', enable_result.stdout)

            delete_result = self.runner.invoke(
                app,
                ["skills", "delete", "release-ops", "--workspace-dir", str(workspace)],
                env=self.env,
            )
            self.assertEqual(delete_result.exit_code, 0)
            self.assertIn('"action": "delete"', delete_result.stdout)
            self.assertFalse(
                (workspace / ".crxzipple" / "skills" / "release-ops").exists(),
            )


if __name__ == "__main__":
    unittest.main()
