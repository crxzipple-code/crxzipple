from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch
import unittest

from crxzipple.core.config import Settings
from crxzipple.modules.tool.infrastructure.runtimes import (
    DockerSandboxBackend,
    SubprocessSandboxBackend,
    build_sandbox_backend,
)


class SandboxBackendTestCase(unittest.TestCase):
    def test_build_sandbox_backend_defaults_to_subprocess(self) -> None:
        settings = Settings(
            app_name="crxzipple",
            environment="test",
            database_url="sqlite:///./test.db",
            sandbox_base_dir="/tmp/crxzipple-sandboxes",
            sandbox_backend="subprocess",
            sandbox_docker_binary="docker",
            sandbox_docker_image="python:3.11-slim",
            log_level="INFO",
            log_json=False,
        )

        backend = build_sandbox_backend(settings)

        self.assertIsInstance(backend, SubprocessSandboxBackend)

    def test_build_sandbox_backend_uses_docker_when_configured(self) -> None:
        settings = Settings(
            app_name="crxzipple",
            environment="test",
            database_url="sqlite:///./test.db",
            sandbox_base_dir="/tmp/crxzipple-sandboxes",
            sandbox_backend="docker",
            sandbox_docker_binary="docker",
            sandbox_docker_image="python:3.11-slim",
            log_level="INFO",
            log_json=False,
        )

        backend = build_sandbox_backend(settings)

        self.assertIsInstance(backend, DockerSandboxBackend)

    def test_docker_sandbox_backend_builds_expected_command(self) -> None:
        with tempfile.TemporaryDirectory() as sandbox_base_dir:
            settings = Settings(
                app_name="crxzipple",
                environment="test",
                database_url="sqlite:///./test.db",
                sandbox_base_dir=sandbox_base_dir,
                sandbox_backend="docker",
                sandbox_docker_binary="docker",
                sandbox_docker_image="python:3.11-slim",
                log_level="INFO",
                log_json=False,
            )
            backend = DockerSandboxBackend(settings)

            with patch(
                "crxzipple.modules.tool.infrastructure.runtimes.sandbox_backends.shutil.which",
                return_value="/usr/bin/docker",
            ), patch(
                "crxzipple.modules.tool.infrastructure.runtimes.sandbox_backends.subprocess.run",
            ) as run_mock:
                run_mock.return_value = subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout='{"ok": true}',
                    stderr="",
                )

                payload = backend.execute(
                    "sandbox.echo",
                    30,
                    {"message": "hello"},
                )

            self.assertEqual(payload, {"ok": True})
            command = run_mock.call_args.args[0]
            self.assertEqual(command[:3], ["docker", "run", "--rm"])
            self.assertIn("--interactive", command)
            self.assertIn("python:3.11-slim", command)
            self.assertIn("python", command)
            self.assertIn("-m", command)
            self.assertIn(
                "crxzipple.modules.tool.infrastructure.runtimes.sandbox_worker",
                command,
            )

            volume_args = [
                command[index + 1]
                for index, token in enumerate(command)
                if token == "--volume"
            ]
            self.assertEqual(len(volume_args), 2)
            self.assertTrue(volume_args[0].endswith(":/workspace/project:ro"))
            self.assertTrue(volume_args[1].endswith(":/workspace/sandbox"))

            run_kwargs = run_mock.call_args.kwargs
            self.assertEqual(run_kwargs["timeout"], 30)
            self.assertEqual(
                run_kwargs["input"],
                '{"arguments": {"message": "hello"}, "execution_context": null}',
            )
            self.assertEqual(Path(run_kwargs["cwd"]).parent, Path(sandbox_base_dir))


if __name__ == "__main__":
    unittest.main()
