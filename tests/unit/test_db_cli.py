from __future__ import annotations

from tests.unit.cli_test_support import *


class DbCliTestCase(CliModuleTestCase):
    def test_db_commands_apply_and_report_revisions(self) -> None:
            harness = SqliteTestHarness()
            env = {"APP_DATABASE_URL": harness.database_url}
            database_path = harness.database_url.removeprefix("sqlite:///")

            try:
                upgrade_result = self.runner.invoke(app, ["db", "upgrade"], env=env)

                self.assertEqual(upgrade_result.exit_code, 0)

                with sqlite3.connect(database_path) as connection:
                    tables = {
                        row[0]
                        for row in connection.execute(
                            "SELECT name FROM sqlite_master WHERE type = 'table'",
                        )
                    }
                    message_columns = {
                        row[1]
                        for row in connection.execute("PRAGMA table_info(session_messages)")
                    }
                    revision = connection.execute(
                        "SELECT version_num FROM alembic_version",
                    ).fetchone()

                self.assertNotIn("tools", tables)
                self.assertIn("tool_runs", tables)
                self.assertIn("sessions", tables)
                self.assertIn("session_messages", tables)
                self.assertIn("session_instances", tables)
                self.assertIn("orchestration_runs", tables)
                self.assertTrue(
                    {
                        "sequence_no",
                        "kind",
                        "content_payload",
                        "source_kind",
                        "source_id",
                        "visibility",
                    }.issubset(message_columns),
                )
                self.assertEqual(revision[0], HEAD_REVISION)

                current_result = self.runner.invoke(app, ["db", "current"], env=env)
                history_result = self.runner.invoke(app, ["db", "history"], env=env)

                self.assertEqual(current_result.exit_code, 0)
                self.assertEqual(history_result.exit_code, 0)
                self.assertIn(HEAD_REVISION, current_result.output)
                self.assertIn(HEAD_REVISION, history_result.output)
            finally:
                harness.close()

    def test_db_downgrade_returns_schema_to_base(self) -> None:
            harness = SqliteTestHarness()
            env = {"APP_DATABASE_URL": harness.database_url}
            database_path = harness.database_url.removeprefix("sqlite:///")

            try:
                upgrade_result = self.runner.invoke(app, ["db", "upgrade"], env=env)
                self.assertEqual(upgrade_result.exit_code, 0)

                downgrade_result = self.runner.invoke(
                    app,
                    ["db", "downgrade", "base"],
                    env=env,
                )
                self.assertEqual(downgrade_result.exit_code, 0)

                with sqlite3.connect(database_path) as connection:
                    tables = {
                        row[0]
                        for row in connection.execute(
                            "SELECT name FROM sqlite_master WHERE type = 'table'",
                        )
                    }
                    revision = connection.execute(
                        "SELECT version_num FROM alembic_version",
                    ).fetchone()

                self.assertNotIn("tools", tables)
                self.assertNotIn("tool_runs", tables)
                self.assertNotIn("sessions", tables)
                self.assertNotIn("session_messages", tables)
                self.assertNotIn("session_instances", tables)
                self.assertNotIn("orchestration_runs", tables)
                self.assertIn("alembic_version", tables)
                self.assertIsNone(revision)
            finally:
                harness.close()

    def test_db_revision_autogenerate_creates_file_in_custom_script_location(self) -> None:
            harness = SqliteTestHarness()
            env = {"APP_DATABASE_URL": harness.database_url}

            with tempfile.TemporaryDirectory() as tempdir:
                temp_alembic_dir = Path(tempdir) / "alembic"
                shutil.copytree(db_cli.ALEMBIC_SCRIPT_PATH, temp_alembic_dir)
                env["APP_ALEMBIC_SCRIPT_LOCATION"] = str(temp_alembic_dir)

                versions_dir = temp_alembic_dir / "versions"
                before = {path.name for path in versions_dir.glob("*.py")}

                try:
                    upgrade_result = self.runner.invoke(app, ["db", "upgrade"], env=env)
                    self.assertEqual(upgrade_result.exit_code, 0)

                    revision_result = self.runner.invoke(
                        app,
                        ["db", "revision", "noop drift check", "--autogenerate"],
                        env=env,
                    )

                    self.assertEqual(revision_result.exit_code, 0)

                    after = {path.name for path in versions_dir.glob("*.py")}
                    created = after - before

                    self.assertEqual(len(created), 1)
                    created_path = versions_dir / created.pop()
                    self.assertIn("noop_drift_check", created_path.name)
                    self.assertIn(str(created_path), revision_result.output)
                finally:
                    harness.close()

    def test_db_stamp_marks_revision_without_running_migration(self) -> None:
            harness = SqliteTestHarness()
            env = {"APP_DATABASE_URL": harness.database_url}
            database_path = harness.database_url.removeprefix("sqlite:///")

            try:
                stamp_result = self.runner.invoke(app, ["db", "stamp", "head"], env=env)

                self.assertEqual(stamp_result.exit_code, 0)

                with sqlite3.connect(database_path) as connection:
                    tables = {
                        row[0]
                        for row in connection.execute(
                            "SELECT name FROM sqlite_master WHERE type = 'table'",
                        )
                    }
                    revision = connection.execute(
                        "SELECT version_num FROM alembic_version",
                    ).fetchone()

                self.assertNotIn("tools", tables)
                self.assertNotIn("sessions", tables)
                self.assertNotIn("orchestration_runs", tables)
                self.assertEqual(revision[0], HEAD_REVISION)
                self.assertEqual(tables, {"alembic_version"})
            finally:
                harness.close()

    def test_db_revision_empty_creates_file_in_custom_script_location(self) -> None:
            harness = SqliteTestHarness()
            env = {"APP_DATABASE_URL": harness.database_url}

            with tempfile.TemporaryDirectory() as tempdir:
                temp_alembic_dir = Path(tempdir) / "alembic"
                shutil.copytree(db_cli.ALEMBIC_SCRIPT_PATH, temp_alembic_dir)
                env["APP_ALEMBIC_SCRIPT_LOCATION"] = str(temp_alembic_dir)

                versions_dir = temp_alembic_dir / "versions"
                before = {path.name for path in versions_dir.glob("*.py")}

                try:
                    upgrade_result = self.runner.invoke(app, ["db", "upgrade"], env=env)
                    self.assertEqual(upgrade_result.exit_code, 0)

                    revision_result = self.runner.invoke(
                        app,
                        ["db", "revision-empty", "manual checkpoint"],
                        env=env,
                    )

                    self.assertEqual(revision_result.exit_code, 0)

                    after = {path.name for path in versions_dir.glob("*.py")}
                    created = after - before

                    self.assertEqual(len(created), 1)
                    created_path = versions_dir / created.pop()
                    self.assertIn("manual_checkpoint", created_path.name)
                    self.assertIn(str(created_path), revision_result.output)
                finally:
                    harness.close()


if __name__ == "__main__":
    unittest.main()
