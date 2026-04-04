from __future__ import annotations

import asyncio
from dataclasses import dataclass
import os
from pathlib import Path
import shutil

from tools.workspace.fs_safe import (
    resolve_workspace_root,
    resolve_workspace_search_root,
)


DEFAULT_WORKSPACE_EXEC_TIMEOUT_SECONDS = 20
MAX_WORKSPACE_EXEC_TIMEOUT_SECONDS = 300
MAX_WORKSPACE_EXEC_COMMAND_CHARS = 8_000
MAX_WORKSPACE_EXEC_OUTPUT_CHARS = 12_000


@dataclass(frozen=True, slots=True)
class PreparedWorkspaceCommand:
    workspace_root: str
    working_directory: str
    working_directory_relative: str | None
    shell: str
    command: str
    timeout_seconds: int


@dataclass(frozen=True, slots=True)
class WorkspaceCommandExecution:
    workspace_root: str
    working_directory: str
    working_directory_relative: str | None
    shell: str
    command: str
    exit_code: int
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool
    timeout_seconds: int


async def execute_workspace_command(
    *,
    workspace_dir: str | None,
    command: str,
    cwd: str | None = None,
    timeout_seconds: int = DEFAULT_WORKSPACE_EXEC_TIMEOUT_SECONDS,
) -> WorkspaceCommandExecution:
    prepared = prepare_workspace_command(
        workspace_dir=workspace_dir,
        command=command,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
    )
    return await execute_prepared_workspace_command(prepared)


def prepare_workspace_command(
    *,
    workspace_dir: str | None,
    command: str,
    cwd: str | None = None,
    timeout_seconds: int = DEFAULT_WORKSPACE_EXEC_TIMEOUT_SECONDS,
) -> PreparedWorkspaceCommand:
    normalized_command = command.strip()
    if not normalized_command:
        raise ValueError("exec requires a non-empty command.")
    if len(normalized_command) > MAX_WORKSPACE_EXEC_COMMAND_CHARS:
        raise ValueError(
            f"exec command is too long; maximum length is {MAX_WORKSPACE_EXEC_COMMAND_CHARS} characters.",
        )

    normalized_timeout = min(
        max(int(timeout_seconds), 1),
        MAX_WORKSPACE_EXEC_TIMEOUT_SECONDS,
    )
    root = resolve_workspace_root(workspace_dir)
    working_directory, working_directory_relative = _resolve_working_directory(
        root=root,
        cwd=cwd,
    )
    shell = _resolve_shell_executable()
    return PreparedWorkspaceCommand(
        workspace_root=str(root),
        working_directory=str(working_directory),
        working_directory_relative=working_directory_relative,
        shell=shell,
        command=normalized_command,
        timeout_seconds=normalized_timeout,
    )


async def execute_prepared_workspace_command(
    prepared: PreparedWorkspaceCommand,
) -> WorkspaceCommandExecution:
    try:
        process = await asyncio.create_subprocess_exec(
            prepared.shell,
            "-lc",
            prepared.command,
            cwd=prepared.working_directory,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        raise ValueError("Workspace command could not be started.") from exc

    try:
        stdout_raw, stderr_raw = await asyncio.wait_for(
            process.communicate(),
            timeout=prepared.timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.communicate()
        raise ValueError(
            f"Workspace command timed out after {prepared.timeout_seconds} seconds.",
        ) from exc

    if process.returncode is None:
        raise ValueError("Workspace command did not report an exit code.")

    stdout, stdout_truncated = _truncate_output(_decode_output(stdout_raw))
    stderr, stderr_truncated = _truncate_output(_decode_output(stderr_raw))
    return WorkspaceCommandExecution(
        workspace_root=prepared.workspace_root,
        working_directory=prepared.working_directory,
        working_directory_relative=prepared.working_directory_relative,
        shell=prepared.shell,
        command=prepared.command,
        exit_code=process.returncode,
        stdout=stdout,
        stderr=stderr,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
        timeout_seconds=prepared.timeout_seconds,
    )


def _resolve_working_directory(*, root: Path, cwd: str | None) -> tuple[Path, str | None]:
    if cwd is None or not cwd.strip() or cwd.strip() == ".":
        return root, None
    candidate, relative = resolve_workspace_search_root(root=root, relative_path=cwd)
    if not candidate.is_dir():
        raise ValueError(
            f"Workspace exec cwd '{relative}' is not a readable directory.",
        )
    return candidate, relative


def _resolve_shell_executable() -> str:
    preferred = os.environ.get("SHELL", "").strip()
    if preferred:
        preferred_name = Path(preferred).name.lower()
        if preferred_name in {"sh", "bash", "zsh"}:
            resolved = shutil.which(preferred)
            if resolved:
                return resolved
    fallback = shutil.which("/bin/sh") or shutil.which("sh")
    if fallback:
        return fallback
    raise ValueError("No POSIX shell is available for workspace exec.")


def _decode_output(raw: bytes | None) -> str:
    if not raw:
        return ""
    return raw.decode("utf-8", errors="replace")


def _truncate_output(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_WORKSPACE_EXEC_OUTPUT_CHARS:
        return text, False
    suffix = "\n... [output truncated]"
    kept = MAX_WORKSPACE_EXEC_OUTPUT_CHARS - len(suffix)
    if kept <= 0:
        return suffix.lstrip(), True
    return f"{text[:kept].rstrip()}{suffix}", True
