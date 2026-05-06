from __future__ import annotations

from tests.unit.cli_test_support import *


class EventRelayCliTestCase(CliModuleTestCase):
    def test_event_relay_process_rejects_sqlite_without_explicit_runtime_fallback(self) -> None:
        result = self.runner.invoke(
            app,
            ["event-relay", "process"],
            env=self.env_without_sqlite_runtime_fallback(),
        )

        self.assertEqual(result.exit_code, 1)
        self.assertIn("Refusing to start event relay with SQLite", result.stderr)
        self.assertIn("APP_ALLOW_SQLITE_RUNTIME_FALLBACK=1", result.stderr)

    def test_event_relay_run_rejects_sqlite_without_explicit_runtime_fallback(self) -> None:
        result = self.runner.invoke(
            app,
            [
                "event-relay",
                "run",
                "--max-idle-cycles",
                "1",
            ],
            env=self.env_without_sqlite_runtime_fallback(),
        )

        self.assertEqual(result.exit_code, 1)
        self.assertIn("Refusing to start event relay with SQLite", result.stderr)
        self.assertIn("APP_ALLOW_SQLITE_RUNTIME_FALLBACK=1", result.stderr)
