from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from crxzipple.interfaces.runtime_container import AppKey
from crxzipple.interfaces.cli.main import app
from crxzipple.modules.channels import ChannelAccountProfile, ChannelProfile
from tests.unit.support import SqliteTestHarness


class ChannelsCliTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()
        self._skills_tempdir = tempfile.TemporaryDirectory()
        skills_root = Path(self._skills_tempdir.name)
        self._global_skills_patcher = patch(
            "crxzipple.modules.skills.infrastructure.filesystem.repository.DEFAULT_GLOBAL_SKILLS_DIR",
            skills_root / "global",
        )
        self._system_skills_patcher = patch(
            "crxzipple.modules.skills.infrastructure.filesystem.repository.DEFAULT_SYSTEM_SKILLS_DIR",
            skills_root / "system",
        )
        self._global_skills_patcher.start()
        self._system_skills_patcher.start()
        self.harness = SqliteTestHarness()
        self.harness.initialize_schema()
        self.env = {
            "APP_DATABASE_URL": self.harness.database_url,
            "APP_TOOL_OPENAPI_PROVIDER_PATHS": os.pathsep,
            "APP_AUTHORIZATION_ENABLED": "false",
            "APP_CHANNELS_STATE_DIR": str(Path(self.harness._tempdir.name) / "channels"),
            "APP_EVENTS_BACKEND": "file",
            "APP_EVENTS_STATE_DIR": str(Path(self.harness._tempdir.name) / "events"),
            "APP_ALLOW_SQLITE_RUNTIME_FALLBACK": "1",
            "APP_ALLOW_FILE_EVENTS_RUNTIME_FALLBACK": "1",
        }

    def tearDown(self) -> None:
        self.harness.close()
        self._system_skills_patcher.stop()
        self._global_skills_patcher.stop()
        self._skills_tempdir.cleanup()

    def env_without_sqlite_runtime_fallback(self) -> dict[str, str]:
        env = dict(self.env)
        env.pop("APP_ALLOW_SQLITE_RUNTIME_FALLBACK", None)
        return env

    def test_channel_profile_cli_upsert_disable_enable_uses_channels_store(self) -> None:
        upsert = self.runner.invoke(
            app,
            [
                "channel-runtime",
                "upsert-profile",
                "web",
                "--capabilities-json",
                '{"supports_streaming": true}',
                "--account-json",
                '{"account_id": "browser", "transport_mode": "sse"}',
                "--metadata-json",
                '{"owner": "channels"}',
            ],
            env=self.env,
        )

        self.assertEqual(upsert.exit_code, 0)
        self.assertIn('"channel_type": "web"', upsert.stdout)

        disabled = self.runner.invoke(
            app,
            ["channel-runtime", "disable-profile", "WEB"],
            env=self.env,
        )

        self.assertEqual(disabled.exit_code, 0)
        self.assertIn('"enabled": false', disabled.stdout)

        enabled = self.runner.invoke(
            app,
            ["channel-runtime", "enable-profile", "web"],
            env=self.env,
        )

        self.assertEqual(enabled.exit_code, 0)
        self.assertIn('"enabled": true', enabled.stdout)
        reopened = self.harness.build_runtime_container()
        try:
            profile = reopened.require(AppKey.CHANNEL_PROFILE_SERVICE).get_profile(
                "web",
            )
            self.assertIsNotNone(profile)
            assert profile is not None
            self.assertTrue(profile.enabled)
            self.assertEqual(profile.accounts[0].account_id, "browser")
        finally:
            reopened.close()

    def test_channel_runtime_cli_registers_runtime_from_profile(self) -> None:
        container = self.harness.build_runtime_container()
        try:
            container.require(AppKey.CHANNEL_PROFILE_SERVICE).upsert_profile(
                ChannelProfile(
                    channel_type="web",
                    accounts=(
                        ChannelAccountProfile(
                            account_id="default",
                            transport_mode="sse",
                        ),
                    ),
                ),
            )
        finally:
            container.close()

        result = self.runner.invoke(
            app,
            [
                "channel-runtime",
                "run",
                "--channel",
                "web",
                "--runtime-id",
                "web-runtime-cli-1",
                "--max-cycles",
                "1",
                "--poll-interval-seconds",
                "0.05",
            ],
            env=self.env,
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn('"status": "running"', result.stdout)
        self.assertIn('"runtime_id": "web-runtime-cli-1"', result.stdout)

        reopened = self.harness.build_runtime_container()
        try:
            runtime = reopened.require(AppKey.CHANNEL_RUNTIME_MANAGER).get_runtime(
                "web-runtime-cli-1",
            )
            self.assertIsNone(runtime)
            binding = reopened.require(
                AppKey.CHANNEL_RUNTIME_MANAGER,
            ).resolve_account_binding(
                channel_type="web",
                channel_account_id="default",
            )
            self.assertIsNone(binding)
        finally:
            reopened.close()

    def test_channel_runtime_run_rejects_sqlite_without_explicit_runtime_fallback(
        self,
    ) -> None:
        result = self.runner.invoke(
            app,
            [
                "channel-runtime",
                "run",
                "--channel",
                "web",
                "--runtime-id",
                "web-runtime-cli-guard",
                "--max-cycles",
                "1",
            ],
            env=self.env_without_sqlite_runtime_fallback(),
        )

        self.assertEqual(result.exit_code, 1)
        self.assertIn("Refusing to start channel runtime with SQLite", result.stderr)
        self.assertIn("APP_ALLOW_SQLITE_RUNTIME_FALLBACK=1", result.stderr)
