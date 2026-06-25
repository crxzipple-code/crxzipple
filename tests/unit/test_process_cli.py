from __future__ import annotations

import json
import tempfile
import time
import unittest

from tests.unit.cli_test_support import CliModuleTestCase


class ProcessCliTestCase(CliModuleTestCase):
    def test_process_cli_starts_lists_reads_and_removes_processes(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            start_result = self.invoke_cli(
                [
                    "process",
                    "start",
                    "printf 'hello\\n'; sleep 0.05; printf 'done\\n'",
                    "--working-directory",
                    tempdir,
                    "--session-key",
                    "agent:assistant:main",
                ],
            )
            self.assertEqual(start_result.exit_code, 0)
            start_payload = json.loads(start_result.stdout)
            process_id = start_payload["id"]

            list_result = self.invoke_cli(
                ["process", "list", "--session-key", "agent:assistant:main"],
            )
            self.assertEqual(list_result.exit_code, 0)
            list_payload = json.loads(list_result.stdout)
            self.assertEqual([item["id"] for item in list_payload], [process_id])

            deadline = time.monotonic() + 0.5
            while True:
                output_result = self.invoke_cli(
                    ["process", "output", process_id],
                )
                self.assertEqual(output_result.exit_code, 0)
                output_payload = json.loads(output_result.stdout)
                if "done" in output_payload["stdout"]:
                    break
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.02)
            self.assertEqual(output_result.exit_code, 0)
            self.assertIn("hello", output_payload["stdout"])
            self.assertIn("done", output_payload["stdout"])

            remove_result = self.invoke_cli(
                ["process", "remove", process_id],
            )
            self.assertEqual(remove_result.exit_code, 0)
            remove_payload = json.loads(remove_result.stdout)
            self.assertTrue(remove_payload["removed"])

    def test_process_cli_can_terminate_running_process(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            start_result = self.invoke_cli(
                [
                    "process",
                    "start",
                    "sleep 5",
                    "--working-directory",
                    tempdir,
                ],
            )
            self.assertEqual(start_result.exit_code, 0)
            process_id = json.loads(start_result.stdout)["id"]

            terminate_result = self.invoke_cli(
                ["process", "terminate", process_id],
            )
            self.assertEqual(terminate_result.exit_code, 0)

            get_result = self.invoke_cli(
                ["process", "get", process_id],
            )
            self.assertEqual(get_result.exit_code, 0)
            get_payload = json.loads(get_result.stdout)
            self.assertIn(get_payload["status"], {"exited", "failed", "killed"})


if __name__ == "__main__":
    unittest.main()
