from __future__ import annotations

import os
from typing import Any

from crxzipple.modules.tool.domain import ToolExecutionContext, ToolRunResult


async def _sandbox_echo_handler(
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None = None,
) -> ToolRunResult:
    del execution_context
    return ToolRunResult.text(
        str(arguments.get("message") or ""),
        details={
            "received": dict(arguments),
            "message": arguments.get("message"),
        },
        metadata={
            "tool": "sandbox.echo",
            "environment": "sandbox",
            "sandboxed": os.getenv("CRXZIPPLE_SANDBOX") == "true",
            "process_id": os.getpid(),
            "working_directory": os.getcwd(),
        },
    )


def sandbox_echo(_container: Any):
    return _sandbox_echo_handler
