from __future__ import annotations

import asyncio
import os
from pathlib import Path

from tools.command.command_exec import execute_workspace_command


def test_workspace_exec_prefers_crxzipple_python_bin_for_python3(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime_bin = tmp_path / "runtime" / "bin"
    runtime_bin.mkdir(parents=True)
    runtime_python = runtime_bin / "python"
    runtime_python.write_text("#!/bin/sh\necho runtime-python\n", encoding="utf-8")
    runtime_python.chmod(0o755)
    runtime_python3 = runtime_bin / "python3"
    runtime_python3.write_text("#!/bin/sh\necho runtime-python3\n", encoding="utf-8")
    runtime_python3.chmod(0o755)

    fallback_bin = tmp_path / "fallback" / "bin"
    fallback_bin.mkdir(parents=True)
    fallback_python3 = fallback_bin / "python3"
    fallback_python3.write_text("#!/bin/sh\necho fallback-python3\n", encoding="utf-8")
    fallback_python3.chmod(0o755)

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("CRXZIPPLE_PYTHON", str(runtime_python))
    monkeypatch.setenv("PATH", str(fallback_bin))

    result = asyncio.run(
        execute_workspace_command(
            workspace_dir=str(workspace),
            command="python3",
            timeout_seconds=5,
        ),
    )

    assert result.exit_code == 0
    assert result.stdout.strip() == "runtime-python3"
    assert os.environ["PATH"] == str(fallback_bin)
