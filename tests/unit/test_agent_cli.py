from __future__ import annotations

from tests.unit.cli_test_support import *


class AgentCliTestCase(CliModuleTestCase):
    def test_agent_cli_registers_and_lists_profiles(self) -> None:
            register_result = self.runner.invoke(
                app,
                [
                    "agent",
                    "register-profile",
                    "writer",
                    "Writer",
                    "openai.gpt-5.4-mini",
                    "--description",
                    "Writes concise summaries.",
                    "--display-name",
                    "Writer Agent",
                    "--stream-by-default",
                    "--workspace",
                    "/tmp/workspace",
                ],
                env=self.env,
            )

            self.assertEqual(register_result.exit_code, 0)
            self.assertIn('"id": "writer"', register_result.stdout)
            self.assertIn('"display_name": "Writer Agent"', register_result.stdout)

            list_result = self.runner.invoke(app, ["agent", "list"], env=self.env)
            get_result = self.runner.invoke(app, ["agent", "get", "writer"], env=self.env)

            self.assertEqual(list_result.exit_code, 0)
            self.assertEqual(get_result.exit_code, 0)
            self.assertIn('"name": "Writer"', list_result.stdout)
            self.assertIn('"default_llm_id": "openai.gpt-5.4-mini"', get_result.stdout)

    def test_agent_cli_migrates_profile_home(self) -> None:
            with tempfile.TemporaryDirectory() as tempdir:
                root = Path(tempdir)
                workspace = root / "legacy-workspace"
                home_dir = root / "agent-home"
                (workspace / "memory").mkdir(parents=True)
                (workspace / "AGENTS.md").write_text("legacy rules", encoding="utf-8")
                (workspace / "memory" / "notes.md").write_text(
                    "remember this",
                    encoding="utf-8",
                )

                register_result = self.runner.invoke(
                    app,
                    [
                        "agent",
                        "register-profile",
                        "writer",
                        "Writer",
                        "openai.gpt-5.4-mini",
                        "--workspace",
                        str(workspace),
                    ],
                    env=self.env,
                )
                self.assertEqual(register_result.exit_code, 0)

                migrate_result = self.runner.invoke(
                    app,
                    [
                        "agent",
                        "migrate-home",
                        "writer",
                        str(home_dir),
                    ],
                    env=self.env,
                )

                self.assertEqual(migrate_result.exit_code, 0)
                self.assertIn('"source_dir":', migrate_result.stdout)
                self.assertIn(str(home_dir), migrate_result.stdout)
                self.assertIn('AGENTS.md -> AGENT.md', migrate_result.stdout)
                self.assertTrue((home_dir / "agent.json").is_file())
                self.assertEqual(
                    (home_dir / "AGENT.md").read_text(encoding="utf-8"),
                    "legacy rules",
                )
                self.assertEqual(
                    (home_dir / "memory" / "notes.md").read_text(encoding="utf-8"),
                    "remember this",
                )

                get_result = self.runner.invoke(app, ["agent", "get", "writer"], env=self.env)
                self.assertEqual(get_result.exit_code, 0)
                self.assertIn(f'"home_dir": "{home_dir}"', get_result.stdout)
                self.assertIn(f'"workdir": "{workspace}"', get_result.stdout)

    def test_agent_cli_exports_and_syncs_home_config(self) -> None:
            with tempfile.TemporaryDirectory() as tempdir:
                root = Path(tempdir)
                home_dir = root / "agent-home"
                workdir = root / "workdir"

                register_result = self.runner.invoke(
                    app,
                    [
                        "agent",
                        "register-profile",
                        "writer",
                        "Writer",
                        "openai.gpt-5.4-mini",
                        "--home-dir",
                        str(home_dir),
                        "--workdir",
                        str(workdir),
                    ],
                    env=self.env,
                )
                self.assertEqual(register_result.exit_code, 0)

                export_result = self.runner.invoke(
                    app,
                    ["agent", "export-home", "writer"],
                    env=self.env,
                )
                self.assertEqual(export_result.exit_code, 0)
                self.assertIn(str(home_dir), export_result.stdout)

                config_path = home_dir / "agent.json"
                payload = json.loads(config_path.read_text(encoding="utf-8"))
                payload["name"] = "Writer Exported"
                payload["llm_routing_policy"]["default_llm_id"] = "openai.gpt-5.4"
                payload["runtime_preferences"]["workdir"] = str(root / "project-c")
                config_path.write_text(
                    json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )

                sync_result = self.runner.invoke(
                    app,
                    ["agent", "sync-home", "writer"],
                    env=self.env,
                )
                self.assertEqual(sync_result.exit_code, 0)
                self.assertIn('"name": "Writer Exported"', sync_result.stdout)
                self.assertIn('"default_llm_id": "openai.gpt-5.4"', sync_result.stdout)
                self.assertIn(str(root / "project-c"), sync_result.stdout)

    def test_agent_cli_syncs_legacy_home_config_shape(self) -> None:
            with tempfile.TemporaryDirectory() as tempdir:
                root = Path(tempdir)
                home_dir = root / "agent-home"

                register_result = self.runner.invoke(
                    app,
                    [
                        "agent",
                        "register-profile",
                        "writer",
                        "Writer",
                        "openai.gpt-5.4-mini",
                        "--home-dir",
                        str(home_dir),
                    ],
                    env=self.env,
                )
                self.assertEqual(register_result.exit_code, 0)

                config_path = home_dir / "agent.json"
                config_path.write_text(
                    json.dumps(
                        {
                            "id": "writer",
                            "name": "Legacy Writer",
                            "default_llm_id": "openai.gpt-5.4",
                            "workdir": str(root / "legacy-workdir"),
                        },
                        ensure_ascii=True,
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )

                sync_result = self.runner.invoke(
                    app,
                    ["agent", "sync-home", "writer"],
                    env=self.env,
                )
                self.assertEqual(sync_result.exit_code, 0)
                self.assertIn('"name": "Legacy Writer"', sync_result.stdout)
                self.assertIn('"default_llm_id": "openai.gpt-5.4"', sync_result.stdout)
                self.assertIn(str(root / "legacy-workdir"), sync_result.stdout)

    def test_agent_sync_profiles_loads_yaml_configs_with_defaults(self) -> None:
            env = dict(self.env)

            with tempfile.TemporaryDirectory() as tempdir:
                profiles_dir = Path(tempdir) / "agent_profiles"
                profiles_dir.mkdir()
                (profiles_dir / "defaults.yaml").write_text(
                    "\n".join(
                        [
                            "defaults:",
                            "  description: Default agent profile description.",
                            "  instruction_policy:",
                            "    stream_by_default: true",
                            "    response_style: concise",
                            "  llm_routing_policy:",
                            "    default_llm_id: openai.gpt-5.4-mini",
                            "  execution_policy:",
                            "    timeout_seconds: 180",
                            "    max_turns: 9",
                            "  runtime_preferences:",
                            "    sandbox_mode: sandbox",
                            "profiles:",
                            "  - id: writer",
                            "    name: Writer",
                            "    identity:",
                            "      display_name: Writer Agent",
                            "",
                        ],
                    ),
                    encoding="utf-8",
                )
                env["APP_AGENT_PROFILE_PATHS"] = str(profiles_dir)

                sync_result = self.runner.invoke(
                    app,
                    ["agent", "sync-profiles"],
                    env=env,
                )

                self.assertEqual(sync_result.exit_code, 0)
                sync_payload = json.loads(sync_result.stdout)
                self.assertEqual([item["id"] for item in sync_payload], ["writer"])
                self.assertEqual(
                    sync_payload[0]["llm_routing_policy"]["default_llm_id"],
                    "openai.gpt-5.4-mini",
                )
                self.assertTrue(sync_payload[0]["instruction_policy"]["stream_by_default"])
                self.assertEqual(
                    sync_payload[0]["runtime_preferences"]["sandbox_mode"],
                    "sandbox",
                )

                get_result = self.runner.invoke(app, ["agent", "get", "writer"], env=env)
                self.assertEqual(get_result.exit_code, 0)
                get_payload = json.loads(get_result.stdout)
                self.assertEqual(
                    get_payload["identity"]["display_name"],
                    "Writer Agent",
                )
                self.assertEqual(get_payload["execution_policy"]["timeout_seconds"], 180)


if __name__ == "__main__":
    unittest.main()
