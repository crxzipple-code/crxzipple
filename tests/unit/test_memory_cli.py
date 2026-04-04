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


if __name__ == "__main__":
    unittest.main()
