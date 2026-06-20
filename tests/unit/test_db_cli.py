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
                    session_item_columns = {
                        row[1]
                        for row in connection.execute("PRAGMA table_info(session_items)")
                    }
                    session_columns = {
                        row[1]
                        for row in connection.execute("PRAGMA table_info(sessions)")
                    }
                    orchestration_run_columns = {
                        row[1]
                        for row in connection.execute("PRAGMA table_info(orchestration_runs)")
                    }
                    tool_run_columns = {
                        row[1]
                        for row in connection.execute("PRAGMA table_info(tool_runs)")
                    }
                    orchestration_run_indexes = {
                        row[1]
                        for row in connection.execute("PRAGMA index_list(orchestration_runs)")
                    }
                    revision = connection.execute(
                        "SELECT version_num FROM alembic_version",
                    ).fetchone()

                self.assertNotIn("tools", tables)
                self.assertIn("tool_sources", tables)
                self.assertIn("tool_functions", tables)
                self.assertIn("tool_provider_backends", tables)
                self.assertIn("tool_runs", tables)
                self.assertIn("tool_run_assignments", tables)
                self.assertIn("tool_workers", tables)
                self.assertIn("metadata_payload", tool_run_columns)
                self.assertTrue(
                    {
                        "function_id",
                        "function_revision",
                        "source_id",
                        "source_revision",
                        "schema_hash",
                    }.issubset(tool_run_columns),
                )
                self.assertIn("sessions", tables)
                self.assertNotIn("session_messages", tables)
                self.assertIn("session_items", tables)
                self.assertIn("session_instances", tables)
                self.assertIn("orchestration_runs", tables)
                self.assertIn("orchestration_execution_chains", tables)
                self.assertIn("orchestration_execution_steps", tables)
                self.assertIn("orchestration_execution_step_items", tables)
                self.assertIn("event_outbox_records", tables)
                self.assertTrue(
                    {
                        "sequence_no",
                        "kind",
                        "role",
                        "phase",
                        "content_payload",
                        "source_module",
                        "source_kind",
                        "source_id",
                        "provider_item_id",
                        "provider_item_type",
                        "call_id",
                        "tool_name",
                        "metadata_payload",
                    }.issubset(session_item_columns),
                )
                self.assertIn("reply_payload", session_columns)
                self.assertNotIn("delivery_payload", session_columns)
                self.assertIn("reply_target_payload", orchestration_run_columns)
                self.assertNotIn("delivery_target_payload", orchestration_run_columns)
                self.assertIn("lane_lock_key", orchestration_run_columns)
                self.assertTrue(
                    {
                        "pending_approval_request_payload",
                        "last_approval_resolution_payload",
                        "recovery_contract_payload",
                    }.issubset(orchestration_run_columns),
                )
                self.assertIn(
                    "uq_orchestration_runs_active_lane",
                    orchestration_run_indexes,
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

    def test_db_upgrade_migrates_run_wait_state_out_of_metadata(self) -> None:
            harness = SqliteTestHarness()
            env = {"APP_DATABASE_URL": harness.database_url}
            database_path = harness.database_url.removeprefix("sqlite:///")

            try:
                upgrade_0067 = self.runner.invoke(
                    app,
                    ["db", "upgrade", "0067_event_outbox"],
                    env=env,
                )
                self.assertEqual(upgrade_0067.exit_code, 0)

                pending_approval = {
                    "request_id": "approval-migrate",
                    "effect_id": "workspace_search",
                    "label": "Workspace Search",
                    "tool_ids": ["workspace_search"],
                }
                last_resolution = {
                    "request_id": "approval-migrate",
                    "decision": "allow_once",
                }
                recovery_contract = {
                    "kind": "approval",
                    "state": "resolved_allow_pending_replay",
                }
                with sqlite3.connect(database_path) as connection:
                    connection.execute(
                        """
                        INSERT INTO orchestration_runs (
                            id,
                            status,
                            stage,
                            queue_policy,
                            priority,
                            current_step,
                            max_steps,
                            pending_tool_run_ids,
                            inbound_instruction_payload,
                            metadata_payload,
                            created_at,
                            updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            "run-wait-state-migration",
                            "waiting",
                            "waiting_for_confirmation",
                            "fifo",
                            100,
                            0,
                            99,
                            json.dumps([]),
                            json.dumps({"source": "cli", "content": "hello"}),
                            json.dumps(
                                {
                                    "session_key": "agent:assistant:main",
                                    "pending_approval_request": pending_approval,
                                    "last_approval_resolution": last_resolution,
                                    "recovery_contract": recovery_contract,
                                },
                            ),
                            "2026-06-02T00:00:00+00:00",
                            "2026-06-02T00:00:00+00:00",
                        ),
                    )
                    connection.commit()

                upgrade_head = self.runner.invoke(app, ["db", "upgrade"], env=env)
                self.assertEqual(upgrade_head.exit_code, 0)

                with sqlite3.connect(database_path) as connection:
                    row = connection.execute(
                        """
                        SELECT
                            metadata_payload,
                            pending_approval_request_payload,
                            last_approval_resolution_payload,
                            recovery_contract_payload
                        FROM orchestration_runs
                        WHERE id = ?
                        """,
                        ("run-wait-state-migration",),
                    ).fetchone()

                assert row is not None
                metadata = json.loads(row[0])
                self.assertNotIn("pending_approval_request", metadata)
                self.assertNotIn("last_approval_resolution", metadata)
                self.assertNotIn("recovery_contract", metadata)
                self.assertEqual(json.loads(row[1]), pending_approval)
                self.assertEqual(json.loads(row[2]), last_resolution)
                self.assertEqual(json.loads(row[3]), recovery_contract)
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
                self.assertNotIn("tool_sources", tables)
                self.assertNotIn("tool_functions", tables)
                self.assertNotIn("tool_provider_backends", tables)
                self.assertNotIn("tool_runs", tables)
                self.assertNotIn("tool_run_assignments", tables)
                self.assertNotIn("tool_workers", tables)
                self.assertNotIn("sessions", tables)
                self.assertNotIn("session_messages", tables)
                self.assertNotIn("session_items", tables)
                self.assertNotIn("session_instances", tables)
                self.assertNotIn("orchestration_runs", tables)
                self.assertNotIn("orchestration_execution_chains", tables)
                self.assertNotIn("orchestration_execution_steps", tables)
                self.assertNotIn("orchestration_execution_step_items", tables)
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
