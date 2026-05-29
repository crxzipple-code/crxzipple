from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Protocol

from crxzipple.core.config import Settings
from crxzipple.modules.tool.domain import ToolExecutionContext, ToolRunResult


class SandboxBackend(Protocol):
    def execute(
        self,
        runtime_key: str,
        timeout_seconds: int,
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> Any:
        ...


class SubprocessSandboxBackend:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._worker_module = "crxzipple.modules.tool.infrastructure.runtimes.sandbox_worker"
        self._project_root = Path(__file__).resolve().parents[6]
        self._project_src = self._project_root / "src"

    def execute(
        self,
        runtime_key: str,
        timeout_seconds: int,
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> Any:
        sandbox_base_dir = Path(self.settings.sandbox_base_dir)
        sandbox_base_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(
            prefix="tool-sandbox-",
            dir=sandbox_base_dir,
        ) as sandbox_dir:
            result = subprocess.run(
                [sys.executable, "-m", self._worker_module, runtime_key],
                input=json.dumps(
                    {
                        "arguments": arguments,
                        "execution_context": (
                            execution_context.to_payload()
                            if execution_context is not None
                            else None
                        ),
                    },
                    ensure_ascii=True,
                ),
                text=True,
                capture_output=True,
                cwd=sandbox_dir,
                env=self._build_sandbox_env(),
                timeout=timeout_seconds,
                check=False,
            )

        return _decode_result(
            runtime_key=runtime_key,
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
        )

    def _build_sandbox_env(self) -> dict[str, str]:
        env = {
            "APP_LOG_LEVEL": self.settings.log_level,
            "APP_LOG_JSON": "true" if self.settings.log_json else "false",
            "APP_SANDBOX_BASE_DIR": self.settings.sandbox_base_dir,
            "APP_SANDBOX_BACKEND": self.settings.sandbox_backend,
            "APP_SANDBOX_DOCKER_BINARY": self.settings.sandbox_docker_binary,
            "APP_SANDBOX_DOCKER_IMAGE": self.settings.sandbox_docker_image,
            "CRXZIPPLE_SANDBOX": "true",
            "PYTHONPATH": os.pathsep.join([str(self._project_root), str(self._project_src)]),
        }
        pythonpath = getattr(os, "environ").get("PYTHONPATH")
        if pythonpath:
            env["PYTHONPATH"] = os.pathsep.join(
                [str(self._project_root), str(self._project_src), pythonpath],
            )
        return env


class DockerSandboxBackend:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._worker_module = "crxzipple.modules.tool.infrastructure.runtimes.sandbox_worker"
        self._project_root = Path(__file__).resolve().parents[6]
        self._project_src = self._project_root / "src"

    def execute(
        self,
        runtime_key: str,
        timeout_seconds: int,
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> Any:
        if shutil.which(self.settings.sandbox_docker_binary) is None:
            raise RuntimeError(
                f"Docker sandbox backend requires '{self.settings.sandbox_docker_binary}' to be installed.",
            )

        sandbox_base_dir = Path(self.settings.sandbox_base_dir)
        sandbox_base_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(
            prefix="tool-sandbox-",
            dir=sandbox_base_dir,
        ) as sandbox_dir:
            command = self._build_command(runtime_key, sandbox_dir)
            result = subprocess.run(
                command,
                input=json.dumps(
                    {
                        "arguments": arguments,
                        "execution_context": (
                            execution_context.to_payload()
                            if execution_context is not None
                            else None
                        ),
                    },
                    ensure_ascii=True,
                ),
                text=True,
                capture_output=True,
                cwd=sandbox_dir,
                timeout=timeout_seconds,
                check=False,
            )

        return _decode_result(
            runtime_key=runtime_key,
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
        )

    def _build_command(self, runtime_key: str, sandbox_dir: str) -> list[str]:
        return [
            self.settings.sandbox_docker_binary,
            "run",
            "--rm",
            "--interactive",
            "--workdir",
            "/workspace/sandbox",
            "--env",
            "APP_LOG_LEVEL=" + self.settings.log_level,
            "--env",
            "APP_LOG_JSON=" + ("true" if self.settings.log_json else "false"),
            "--env",
            "CRXZIPPLE_SANDBOX=true",
            "--env",
            "PYTHONPATH=/workspace/project:/workspace/project/src",
            "--volume",
            f"{self._project_root}:/workspace/project:ro",
            "--volume",
            f"{sandbox_dir}:/workspace/sandbox",
            self.settings.sandbox_docker_image,
            "python",
            "-m",
            self._worker_module,
            runtime_key,
        ]


def build_sandbox_backend(settings: Settings) -> SandboxBackend:
    if settings.sandbox_backend == "subprocess":
        return SubprocessSandboxBackend(settings)
    if settings.sandbox_backend == "docker":
        return DockerSandboxBackend(settings)

    raise ValueError(
        "APP_SANDBOX_BACKEND must be either 'subprocess' or 'docker'.",
    )


def _decode_result(
    *,
    runtime_key: str,
    stdout: str,
    stderr: str,
    returncode: int,
) -> Any:
    if returncode != 0:
        detail = stderr.strip() or stdout.strip() or "unknown sandbox failure"
        raise RuntimeError(
            f"Sandbox execution failed for runtime '{runtime_key}': {detail}",
        )

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Sandbox execution returned invalid JSON for runtime '{runtime_key}'.",
        ) from exc
    if isinstance(payload, dict) and payload.get("__crxzipple_tool_run_result__") is True:
        return ToolRunResult.from_payload(payload)
    return payload
