from __future__ import annotations

from tests.unit.cli_test_support import *


class CliInterfaceTestCase(CliModuleTestCase):
    def test_root_help_exposes_module_groups(self) -> None:
        result = self.runner.invoke(app, ["--help"], env=self.env)

        self.assertEqual(result.exit_code, 0)
        self.assertIn("ask", result.stdout)
        self.assertIn("chat", result.stdout)
        self.assertIn("serve", result.stdout)
        self.assertIn("tool", result.stdout)
        self.assertIn("browser", result.stdout)
        self.assertNotRegex(result.stdout, r"(?m)^\s+tool-worker\s")
        self.assertNotRegex(result.stdout, r"(?m)^\s+tool-scheduler\s")
        self.assertNotRegex(result.stdout, r"(?m)^\s+channel-runtime\s")
        self.assertIn("dispatch", result.stdout)
        self.assertIn("orchestration", result.stdout)
        self.assertNotRegex(result.stdout, r"(?m)^\s+orchestration-scheduler\s")
        self.assertNotRegex(result.stdout, r"(?m)^\s+orchestration-executor\s")
        self.assertNotRegex(result.stdout, r"(?m)^\s+operations-observer\s")
        self.assertNotRegex(result.stdout, r"(?m)^\s+orchestration-worker\s")
        self.assertIn("session", result.stdout)
        self.assertIn("llm", result.stdout)
        self.assertIn("agent", result.stdout)
        self.assertNotRegex(result.stdout, r"(?m)^\s+process\s")
        self.assertIn("auth", result.stdout)
        self.assertIn("db", result.stdout)

    def test_cli_schema_error_detector_matches_missing_schema_messages(self) -> None:
        self.assertTrue(_is_missing_database_schema_error(RuntimeError("no such table: tools")))
        self.assertTrue(
            _is_missing_database_schema_error(
                RuntimeError("no such column: llm_profiles.context_window_tokens"),
            ),
        )
        self.assertTrue(
            _is_missing_database_schema_error(
                RuntimeError('relation "tools" does not exist'),
            ),
        )
        self.assertFalse(
            _is_missing_database_schema_error(RuntimeError("database is locked")),
        )


if __name__ == "__main__":
    unittest.main()
