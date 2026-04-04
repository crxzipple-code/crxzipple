from __future__ import annotations

from typing import Any

from crxzipple.modules.tool.domain import ToolExecutionContext, ToolRunResult


async def _remote_echo_handler(
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None = None,
) -> ToolRunResult:
    return ToolRunResult.text(
        str(arguments.get("message") or ""),
        details={
            "received": dict(arguments),
            "message": arguments.get("message"),
            "execution_context": (
                execution_context.to_payload() if execution_context is not None else None
            ),
        },
        metadata={
            "tool": "remote.echo",
            "environment": "remote",
        },
    )


def remote_echo(_container: Any):
    return _remote_echo_handler
