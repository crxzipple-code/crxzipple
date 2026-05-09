from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from typer.testing import CliRunner

from crxzipple.interfaces.cli.main import _is_missing_database_schema_error
from crxzipple.interfaces.cli.main import app
from crxzipple.interfaces.cli import db as db_cli
from crxzipple.modules.dispatch.application import (
    CreateDispatchTaskInput,
    EnqueueDispatchTaskInput,
)
from crxzipple.modules.tool.application import RegisterToolInput
from tests.unit.skill_test_support import write_skill_package as _write_skill_package
from tests.unit.support import (
    FakeCdpServer,
    FakeChromeMcpClientPool,
    FakePlaywrightCdpSessionPool,
    SampleApiServer,
    SampleLlmApiServer,
    SqliteTestHarness,
    fixture_path,
    openapi_fixture_path,
    seed_browser_state_root,
)

HEAD_REVISION = "0043_settings_governance"


class CliModuleTestCase(unittest.TestCase):
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
        _write_skill_package(
            skills_root / "system" / "memory-recall",
            name="memory-recall",
            description="Recall durable memory before answering.",
            instructions="# Memory Recall\n\nUse durable memory before answering.\n",
            allowed_tools=("memory_search", "memory_read", "memory_write_daily"),
        )
        self.harness = SqliteTestHarness()
        self.harness.initialize_schema()
        self.env = {
            "APP_DATABASE_URL": self.harness.database_url,
            "APP_TOOL_OPENAPI_PROVIDER_PATHS": os.pathsep,
            "APP_AUTHORIZATION_ENABLED": "false",
            "APP_BROWSER_STATE_DIR": str(Path(self.harness._tempdir.name) / "browser"),
            "APP_DAEMON_STATE_DIR": str(Path(self.harness._tempdir.name) / "daemon"),
            "APP_EVENTS_BACKEND": "file",
            "APP_EVENTS_STATE_DIR": str(Path(self.harness._tempdir.name) / "events"),
            "APP_OPERATIONS_STATE_DIR": str(
                Path(self.harness._tempdir.name) / "operations",
            ),
            "APP_ALLOW_SQLITE_RUNTIME_FALLBACK": "1",
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


__all__ = [
    "CliModuleTestCase",
    "CliRunner",
    "CreateDispatchTaskInput",
    "EnqueueDispatchTaskInput",
    "FakeCdpServer",
    "FakeChromeMcpClientPool",
    "FakePlaywrightCdpSessionPool",
    "HEAD_REVISION",
    "Path",
    "SampleApiServer",
    "SampleLlmApiServer",
    "SqliteTestHarness",
    "RegisterToolInput",
    "_is_missing_database_schema_error",
    "_write_skill_package",
    "app",
    "db_cli",
    "fixture_path",
    "json",
    "openapi_fixture_path",
    "os",
    "patch",
    "shutil",
    "seed_browser_state_root",
    "sqlite3",
    "sys",
    "tempfile",
    "time",
    "unittest",
]
