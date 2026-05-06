from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

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
            "APP_EVENTS_STATE_DIR": str(Path(self.harness._tempdir.name) / "events"),
        }

    def tearDown(self) -> None:
        self.harness.close()
        self._system_skills_patcher.stop()
        self._global_skills_patcher.stop()
        self._skills_tempdir.cleanup()

    def test_channel_runtime_cli_registers_runtime_from_profile(self) -> None:
        container = self.harness.build_container()
        try:
            container.channel_profile_service.upsert_profile(
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
            ],
            env=self.env,
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn('"status": "running"', result.stdout)
        self.assertIn('"runtime_id": "web-runtime-cli-1"', result.stdout)

        reopened = self.harness.build_container()
        try:
            runtime = reopened.channel_runtime_manager.get_runtime("web-runtime-cli-1")
            self.assertIsNone(runtime)
            binding = reopened.channel_runtime_manager.resolve_account_binding(
                channel_type="web",
                channel_account_id="default",
            )
            self.assertIsNone(binding)
        finally:
            reopened.close()
