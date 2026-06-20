from __future__ import annotations

import asyncio
import sys
import tempfile
import time
import unittest
from pathlib import Path

from crxzipple.app import AssemblyTarget
from crxzipple.app.keys import AppKey
from crxzipple.modules.tool.application.result_envelope import (
    TOOL_RESULT_ENVELOPE_METADATA_KEY,
    TOOL_RESULT_ENVELOPE_SCHEMA_VERSION,
    TOOL_RESULT_RAW_OUTPUT_BLOCKS_METADATA_KEY,
)
from crxzipple.modules.tool.domain import ToolExecutionContext
from tests.unit.support import SqliteTestHarness
from tools.command.local import CommandToolDeps, exec as command_exec, process as command_process


class CommandToolsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = SqliteTestHarness()
        self.container = self.harness.build_runtime_container(
            target=AssemblyTarget.TEST,
        )

    def tearDown(self) -> None:
        self.harness.close()

    def test_exec_failure_result_includes_model_visible_runtime_facts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            handler = command_exec(self._deps(temp_dir))
            assert handler is not None

            result = asyncio.run(
                handler(
                    {
                        "command": (
                            f"{sys.executable} -c "
                            "\"import sys; print('bad path', file=sys.stderr); sys.exit(7)\""
                        ),
                    },
                    execution_context=self._context(temp_dir),
                ),
            )

        envelope = result.metadata[TOOL_RESULT_ENVELOPE_METADATA_KEY]
        self.assertEqual(result.metadata["exit_code"], 7)
        self.assertIn("bad path", result.metadata["stderr"])
        self.assertEqual(envelope["schema_version"], TOOL_RESULT_ENVELOPE_SCHEMA_VERSION)
        self.assertEqual(envelope["status"], "error")
        self.assertEqual(envelope["key_facts"]["exit_code"], 7)
        self.assertEqual(envelope["provider_replay_payload"]["exit_code"], 7)
        self.assertIn("bad path", envelope["provider_replay_payload"]["stderr"])
        self.assertIn("absolute_cwd", envelope["provider_replay_payload"])
        self.assertIn("shell", envelope["provider_replay_payload"])

    def test_exec_runtime_probe_result_includes_summary_and_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            handler = command_exec(self._deps(temp_dir))
            assert handler is not None

            result = asyncio.run(
                handler(
                    {
                        "command": (
                            f"{sys.executable} -c "
                            "\"import os, sys; "
                            "print('runtime-probe'); "
                            "print(sys.executable); "
                            "print(os.getcwd())\""
                        ),
                    },
                    execution_context=self._context(temp_dir),
                ),
            )

        envelope = result.metadata[TOOL_RESULT_ENVELOPE_METADATA_KEY]
        self.assertEqual(result.metadata["exit_code"], 0)
        self.assertIn("runtime-probe", result.metadata["stdout"])
        self.assertEqual(envelope["schema_version"], TOOL_RESULT_ENVELOPE_SCHEMA_VERSION)
        self.assertEqual(envelope["status"], "ok")
        self.assertIn("runtime-probe", envelope["summary"])
        self.assertEqual(envelope["key_facts"]["exit_code"], 0)
        self.assertEqual(envelope["provider_replay_payload"]["exit_code"], 0)
        self.assertIn("runtime-probe", envelope["provider_replay_payload"]["stdout"])
        self.assertEqual(envelope["provider_replay_payload"]["stderr"], "")
        self.assertFalse(envelope["truncated"])

    def test_exec_truncated_output_exposes_raw_output_read_handles(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            handler = command_exec(self._deps(temp_dir))
            assert handler is not None

            result = asyncio.run(
                handler(
                    {
                        "command": f"{sys.executable} -c \"print('x' * 2000)\"",
                        "max_output_tokens": 64,
                    },
                    execution_context=self._context(temp_dir),
                ),
            )

        envelope = result.metadata[TOOL_RESULT_ENVELOPE_METADATA_KEY]
        self.assertEqual(envelope["schema_version"], TOOL_RESULT_ENVELOPE_SCHEMA_VERSION)
        self.assertTrue(result.metadata["stdout_truncated"])
        self.assertIn(TOOL_RESULT_RAW_OUTPUT_BLOCKS_METADATA_KEY, result.metadata)
        self.assertTrue(envelope["truncated"])
        self.assertEqual(envelope["read_handles"][0]["kind"], "raw_output_block")
        self.assertEqual(envelope["read_handles"][0]["name"], "stdout")

    def test_background_exec_and_process_poll_expose_process_read_handle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            deps = self._deps(temp_dir)
            exec_handler = command_exec(deps)
            process_handler = command_process(deps)
            assert exec_handler is not None
            assert process_handler is not None

            started = asyncio.run(
                exec_handler(
                    {
                        "command": (
                            f"{sys.executable} -c "
                            "\"import time; print('ready', flush=True); time.sleep(0.2)\""
                        ),
                        "background": True,
                    },
                    execution_context=self._context(temp_dir),
                ),
            )
            process_id = str(started.metadata["process_id"])
            for _ in range(20):
                poll = asyncio.run(
                    process_handler(
                        {"action": "poll", "process_id": process_id},
                        execution_context=self._context(temp_dir),
                    ),
                )
                if "ready" in str(poll.metadata.get("stdout") or ""):
                    break
                time.sleep(0.02)

        started_envelope = started.metadata[TOOL_RESULT_ENVELOPE_METADATA_KEY]
        poll_envelope = poll.metadata[TOOL_RESULT_ENVELOPE_METADATA_KEY]
        self.assertEqual(
            started_envelope["read_handles"][0]["arguments"]["process_id"],
            process_id,
        )
        self.assertEqual(
            poll_envelope["read_handles"][0]["arguments"]["process_id"],
            process_id,
        )
        self.assertIn("ready", poll_envelope["provider_replay_payload"]["stdout"])

    def _deps(self, workspace_dir: str) -> CommandToolDeps:
        return CommandToolDeps(
            session_workspace_lookup=lambda _session_key: workspace_dir,
            process_service=self.container.require(AppKey.PROCESS_SERVICE),
        )

    def _context(self, workspace_dir: str) -> ToolExecutionContext:
        return ToolExecutionContext(
            attrs={
                "session_key": "command-tools-test",
                "workspace_dir": workspace_dir,
            },
        )
