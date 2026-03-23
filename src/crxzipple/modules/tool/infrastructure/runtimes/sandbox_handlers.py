from __future__ import annotations

import os
from typing import Any

from crxzipple.modules.tool.domain import ToolRunResult
from crxzipple.modules.tool.infrastructure.runtimes.registry import ToolRuntimeRegistry


async def _sandbox_echo(arguments: dict[str, Any]) -> ToolRunResult:
    return ToolRunResult(
        content={
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


def register_builtin_sandbox_handlers(registry: ToolRuntimeRegistry) -> None:
    registry.register("sandbox.echo", _sandbox_echo)
