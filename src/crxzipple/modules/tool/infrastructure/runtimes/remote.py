from __future__ import annotations

from typing import Any

from crxzipple.modules.tool.domain import Tool, ToolExecutionContext
from crxzipple.modules.tool.domain.exceptions import ToolExecutionNotSupportedError
from crxzipple.modules.tool.infrastructure.handler_invocation import (
    invoke_tool_handler,
)
from crxzipple.modules.tool.infrastructure.runtimes.registry import ToolRuntimeRegistry


class RemoteAsyncToolExecutor:
    def __init__(self, registry: ToolRuntimeRegistry) -> None:
        self.registry = registry

    async def execute_async(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> Any:
        handler = self.registry.get_handler(tool.resolved_runtime_key())
        if handler is None:
            raise ToolExecutionNotSupportedError(
                f"No remote async handler is registered for tool '{tool.id}'.",
            )
        return await invoke_tool_handler(handler, arguments, execution_context)
