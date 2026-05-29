from __future__ import annotations

from tests.unit.cli_test_support import *


class MemoryCliTestCase(CliModuleTestCase):
    def test_memory_cli_reads_and_writes_file_backed_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            home_dir = Path(tempdir) / "writer-home"

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

            daily_result = self.runner.invoke(
                app,
                [
                    "memory",
                    "write-daily",
                    "writer",
                    "Remember the benchmark plan.",
                    "--title",
                    "Today",
                ],
                env=self.env,
            )
            self.assertEqual(daily_result.exit_code, 0)
            daily_payload = json.loads(daily_result.stdout)
            self.assertTrue(daily_payload["path"].startswith("memory/"))

            long_term_result = self.runner.invoke(
                app,
                [
                    "memory",
                    "write-long-term",
                    "writer",
                    "# Preferences\nUse concise file refs.\n",
                ],
                env=self.env,
            )
            self.assertEqual(long_term_result.exit_code, 0)
            self.assertEqual(json.loads(long_term_result.stdout)["path"], "MEMORY.md")

            overview_result = self.runner.invoke(
                app,
                ["memory", "overview", "writer"],
                env=self.env,
            )
            self.assertEqual(overview_result.exit_code, 0)
            overview_payload = json.loads(overview_result.stdout)
            self.assertEqual(overview_payload["space_id"], "writer")
            self.assertEqual(overview_payload["long_term"]["path"], "MEMORY.md")

            search_result = self.runner.invoke(
                app,
                ["memory", "search", "writer", "benchmark plan"],
                env=self.env,
            )
            self.assertEqual(search_result.exit_code, 0)
            search_payload = json.loads(search_result.stdout)
            self.assertEqual(len(search_payload), 1)
            self.assertEqual(search_payload[0]["path"], daily_payload["path"])

            excerpt_result = self.runner.invoke(
                app,
                [
                    "memory",
                    "excerpt",
                    "writer",
                    daily_payload["path"],
                    "--start-line",
                    "1",
                    "--line-count",
                    "4",
                ],
                env=self.env,
            )
            self.assertEqual(excerpt_result.exit_code, 0)
            excerpt_payload = json.loads(excerpt_result.stdout)
            self.assertEqual(excerpt_payload["path"], daily_payload["path"])
            self.assertIn("benchmark plan", excerpt_payload["text"])

    def test_memory_cli_migrates_legacy_agent_home_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            home_dir = Path(tempdir) / "writer-home"
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
            (home_dir / ".state").mkdir(parents=True, exist_ok=True)
            (home_dir / ".state" / "memory-binding.json").write_text(
                json.dumps({"scope_ref": "team:docs"}),
                encoding="utf-8",
            )
            (home_dir / "MEMORY.md").write_text("legacy memory", encoding="utf-8")

            migrate_result = self.runner.invoke(
                app,
                [
                    "memory",
                    "migrate-legacy-agent-homes",
                    "--agent-id",
                    "writer",
                    "--delete-sidecar",
                ],
                env=self.env,
            )

            self.assertEqual(migrate_result.exit_code, 0)
            payload = json.loads(migrate_result.stdout)
            self.assertEqual(payload["scanned"], 1)
            self.assertEqual(payload["updated_profiles"], 1)
            self.assertEqual(payload["created_spaces"], 1)
            self.assertEqual(payload["copied_files"], 1)
            self.assertFalse((home_dir / ".state" / "memory-binding.json").exists())

            get_result = self.runner.invoke(app, ["agent", "get", "writer"], env=self.env)
            self.assertEqual(get_result.exit_code, 0)
            self.assertEqual(json.loads(get_result.stdout)["memory"]["scope_ref"], "team:docs")

            overview_result = self.runner.invoke(
                app,
                ["memory", "overview", "team:docs"],
                env=self.env,
            )
            self.assertEqual(overview_result.exit_code, 0)
            overview_payload = json.loads(overview_result.stdout)
            self.assertEqual(overview_payload["space_id"], "team:docs")
            self.assertEqual(overview_payload["long_term"]["text"], "legacy memory")


if __name__ == "__main__":
    unittest.main()
