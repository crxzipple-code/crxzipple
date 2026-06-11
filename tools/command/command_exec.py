from __future__ import annotations

import asyncio
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import time

from tools.workspace.fs_safe import (
    resolve_workspace_root,
    resolve_workspace_search_root,
)


DEFAULT_WORKSPACE_EXEC_TIMEOUT_SECONDS = 20
MAX_WORKSPACE_EXEC_TIMEOUT_SECONDS = 300
MAX_WORKSPACE_EXEC_COMMAND_CHARS = 8_000
MAX_WORKSPACE_EXEC_OUTPUT_CHARS = 12_000
MIN_WORKSPACE_EXEC_OUTPUT_CHARS = 256
WORKSPACE_EXEC_TOKEN_CHAR_RATIO = 4


@dataclass(frozen=True, slots=True)
class PreparedWorkspaceCommand:
    workspace_root: str
    working_directory: str
    working_directory_relative: str | None
    shell: str
    command: str
    timeout_seconds: int
    max_output_tokens: int | None
    max_output_chars: int


@dataclass(frozen=True, slots=True)
class WorkspaceCommandExecution:
    workspace_root: str
    working_directory: str
    working_directory_relative: str | None
    shell: str
    command: str
    exit_code: int | None
    timed_out: bool
    wall_time_seconds: float
    stdout: str
    stderr: str
    stdout_raw: str
    stderr_raw: str
    stdout_truncated: bool
    stderr_truncated: bool
    stdout_original_chars: int
    stderr_original_chars: int
    output_truncated: bool
    output_budget_chars: int
    output_budget_tokens: int | None
    output_estimated_tokens: int
    timeout_seconds: int


async def execute_workspace_command(
    *,
    workspace_dir: str | None,
    command: str,
    cwd: str | None = None,
    timeout_seconds: int = DEFAULT_WORKSPACE_EXEC_TIMEOUT_SECONDS,
    max_output_tokens: int | None = None,
) -> WorkspaceCommandExecution:
    prepared = prepare_workspace_command(
        workspace_dir=workspace_dir,
        command=command,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        max_output_tokens=max_output_tokens,
    )
    return await execute_prepared_workspace_command(prepared)


def prepare_workspace_command(
    *,
    workspace_dir: str | None,
    command: str,
    cwd: str | None = None,
    timeout_seconds: int = DEFAULT_WORKSPACE_EXEC_TIMEOUT_SECONDS,
    max_output_tokens: int | None = None,
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
    output_budget_tokens, output_budget_chars = _normalize_output_budget(
        max_output_tokens,
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
        max_output_tokens=output_budget_tokens,
        max_output_chars=output_budget_chars,
    )


async def execute_prepared_workspace_command(
    prepared: PreparedWorkspaceCommand,
) -> WorkspaceCommandExecution:
    started_at = time.monotonic()
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
        timed_out = False
    except asyncio.TimeoutError:
        process.kill()
        stdout_raw, stderr_raw = await process.communicate()
        timed_out = True

    wall_time_seconds = round(time.monotonic() - started_at, 3)

    if process.returncode is None and not timed_out:
        raise ValueError("Workspace command did not report an exit code.")

    stdout_raw_text = _decode_output(stdout_raw)
    stderr_raw_text = _decode_output(stderr_raw)
    if timed_out:
        timeout_notice = (
            f"Workspace command timed out after {prepared.timeout_seconds} seconds."
        )
        stderr_raw_text = (
            f"{stderr_raw_text.rstrip()}\n{timeout_notice}"
            if stderr_raw_text.strip()
            else timeout_notice
        )
    stdout, stderr, stdout_truncated, stderr_truncated = _truncate_combined_output(
        stdout_raw_text,
        stderr_raw_text,
        max_chars=prepared.max_output_chars,
    )
    return WorkspaceCommandExecution(
        workspace_root=prepared.workspace_root,
        working_directory=prepared.working_directory,
        working_directory_relative=prepared.working_directory_relative,
        shell=prepared.shell,
        command=prepared.command,
        exit_code=process.returncode,
        timed_out=timed_out,
        wall_time_seconds=wall_time_seconds,
        stdout=stdout,
        stderr=stderr,
        stdout_raw=stdout_raw_text,
        stderr_raw=stderr_raw_text,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
        stdout_original_chars=len(stdout_raw_text),
        stderr_original_chars=len(stderr_raw_text),
        output_truncated=stdout_truncated or stderr_truncated,
        output_budget_chars=prepared.max_output_chars,
        output_budget_tokens=prepared.max_output_tokens,
        output_estimated_tokens=_estimate_output_tokens(stdout, stderr),
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


def _normalize_output_budget(max_output_tokens: int | None) -> tuple[int | None, int]:
    if max_output_tokens is None:
        return None, MAX_WORKSPACE_EXEC_OUTPUT_CHARS
    normalized_tokens = max(int(max_output_tokens), 1)
    requested_chars = normalized_tokens * WORKSPACE_EXEC_TOKEN_CHAR_RATIO
    return normalized_tokens, min(
        max(requested_chars, MIN_WORKSPACE_EXEC_OUTPUT_CHARS),
        MAX_WORKSPACE_EXEC_OUTPUT_CHARS,
    )


def _estimate_output_tokens(stdout: str, stderr: str) -> int:
    chars = len(stdout) + len(stderr)
    return max(
        1,
        (chars + WORKSPACE_EXEC_TOKEN_CHAR_RATIO - 1)
        // WORKSPACE_EXEC_TOKEN_CHAR_RATIO,
    )


def _truncate_combined_output(
    stdout: str,
    stderr: str,
    *,
    max_chars: int,
) -> tuple[str, str, bool, bool]:
    total_chars = len(stdout) + len(stderr)
    if total_chars <= max_chars:
        return stdout, stderr, False, False
    if not stdout:
        stderr_output, stderr_truncated = _truncate_output(stderr, max_chars=max_chars)
        return stdout, stderr_output, False, stderr_truncated
    if not stderr:
        stdout_output, stdout_truncated = _truncate_output(stdout, max_chars=max_chars)
        return stdout_output, stderr, stdout_truncated, False

    stdout_budget = max(
        MIN_WORKSPACE_EXEC_OUTPUT_CHARS // 2,
        int(max_chars * (len(stdout) / total_chars)),
    )
    stdout_budget = min(stdout_budget, max_chars - 1)
    stderr_budget = max_chars - stdout_budget
    stdout_output, stdout_truncated = _truncate_output(
        stdout,
        max_chars=stdout_budget,
    )
    stderr_output, stderr_truncated = _truncate_output(
        stderr,
        max_chars=stderr_budget,
    )
    return stdout_output, stderr_output, stdout_truncated, stderr_truncated


def _truncate_output(text: str, *, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    suffix = "\n... [output truncated]"
    kept = max_chars - len(suffix)
    if kept <= 0:
        return suffix.lstrip(), True
    return f"{text[:kept].rstrip()}{suffix}", True
