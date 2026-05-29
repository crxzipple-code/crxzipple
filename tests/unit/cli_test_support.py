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
from crxzipple.interfaces.runtime_container import AssemblyTarget
from crxzipple.modules.dispatch.application import (
    CreateDispatchTaskInput,
    EnqueueDispatchTaskInput,
)
from tests.unit.skill_test_support import write_skill_package as _write_skill_package
from tests.unit.support import (
    FakeCdpServer,
    FakePlaywrightCdpSessionPool,
    SampleApiServer,
    SampleLlmApiServer,
    SqliteTestHarness,
    fixture_path,
    openapi_fixture_path,
    seed_browser_state_root,
)

HEAD_REVISION = "0062_drop_retired_browser_local_package_manifest"


class CliModuleTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()
        self._runner_invoke = self.runner.invoke
        self.runner.invoke = self._invoke_with_default_container
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
        self._cli_obj: dict[str, object] | None = None
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

    def cli_obj(self, *, env: dict[str, str] | None = None) -> dict[str, object]:
        if self._cli_obj is None:
            with patch.dict(os.environ, env if env is not None else self.env, clear=False):
                self._cli_obj = {
                    "container": self.harness.build_runtime_container(
                        target=AssemblyTarget.CLI_ADMIN,
                    ),
                }
        return self._cli_obj

    def invoke_cli(
        self,
        args: list[str],
        *,
        env: dict[str, str] | None = None,
    ):
        resolved_env = env if env is not None else self.env
        kwargs: dict[str, object] = {"env": resolved_env}
        if resolved_env is self.env:
            kwargs["obj"] = self.cli_obj(env=resolved_env)
        return self.runner.invoke(
            app,
            args,
            **kwargs,
        )

    def _invoke_with_default_container(self, cli, args=None, *extra_args, **kwargs):  # noqa: ANN001
        if cli is app and kwargs.get("env") is self.env and "obj" not in kwargs:
            kwargs["obj"] = self.cli_obj(env=self.env)
        return self._runner_invoke(cli, args, *extra_args, **kwargs)


__all__ = [
    "CliModuleTestCase",
    "CliRunner",
    "CreateDispatchTaskInput",
    "EnqueueDispatchTaskInput",
    "FakeCdpServer",
    "FakePlaywrightCdpSessionPool",
    "HEAD_REVISION",
    "Path",
    "SampleApiServer",
    "SampleLlmApiServer",
    "SqliteTestHarness",
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
