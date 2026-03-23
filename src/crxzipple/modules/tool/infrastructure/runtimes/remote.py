from __future__ import annotations

from typing import Any

from crxzipple.modules.tool.domain import Tool, ToolRunResult
from crxzipple.modules.tool.domain.exceptions import ToolExecutionNotSupportedError
from crxzipple.modules.tool.infrastructure.runtimes.registry import ToolRuntimeRegistry


class RemoteAsyncToolExecutor:
    def __init__(self, registry: ToolRuntimeRegistry) -> None:
        self.registry = registry

    async def execute_async(
        self,
        tool: Tool,
        arguments: dict[str, Any],
    ) -> Any:
        handler = self.registry.get_handler(tool.resolved_runtime_key())
        if handler is None:
            raise ToolExecutionNotSupportedError(
                f"No remote async handler is registered for tool '{tool.id}'.",
            )
        return await handler(arguments)


async def _remote_echo(arguments: dict[str, Any]) -> ToolRunResult:
    return ToolRunResult(
        content={
            "received": dict(arguments),
            "message": arguments.get("message"),
        },
        metadata={
            "tool": "remote.echo",
            "environment": "remote",
        },
    )


def register_builtin_remote_handlers(registry: ToolRuntimeRegistry) -> None:
    registry.register("remote.echo", _remote_echo)
