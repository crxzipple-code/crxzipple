from __future__ import annotations

import asyncio
import subprocess

from crxzipple.core.config import McpProviderSettings
from crxzipple.modules.tool.domain.exceptions import ToolValidationError

from .mcp_diagnostics import redact_mcp_command, redact_mcp_diagnostic


def start_sync_stdio_process(config: McpProviderSettings) -> subprocess.Popen[str]:
    try:
        return subprocess.Popen(
            config.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        raise ToolValidationError(
            stdio_start_failure_message(config.name, config.command, exc),
        ) from exc


async def start_async_stdio_process(
    config: McpProviderSettings,
) -> asyncio.subprocess.Process:
    try:
        return await asyncio.create_subprocess_exec(
            *config.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        raise ToolValidationError(
            stdio_start_failure_message(config.name, config.command, exc),
        ) from exc


def close_sync_stdio_process(process: subprocess.Popen[str] | None) -> None:
    if process is None:
        return

    if process.stdin is not None and not process.stdin.closed:
        process.stdin.close()

    if process.poll() is not None:
        return

    try:
        process.terminate()
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=1)


async def close_async_stdio_process(
    process: asyncio.subprocess.Process | None,
) -> None:
    if process is None:
        return

    if process.stdin is not None:
        process.stdin.close()
        try:
            await process.stdin.wait_closed()
        except Exception:
            pass

    if process.returncode is not None:
        return

    try:
        process.terminate()
        await asyncio.wait_for(process.wait(), timeout=1)
    except (asyncio.TimeoutError, ProcessLookupError):
        process.kill()
        await asyncio.wait_for(process.wait(), timeout=1)


def stdio_start_failure_message(
    provider_name: str,
    command: object,
    error: object,
) -> str:
    return (
        f"MCP provider '{provider_name}' could not start command "
        f"{redact_mcp_command(command)!r}: {redact_mcp_diagnostic(error)}"
    )


__all__ = [
    "close_async_stdio_process",
    "close_sync_stdio_process",
    "start_async_stdio_process",
    "start_sync_stdio_process",
    "stdio_start_failure_message",
]
