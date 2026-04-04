from __future__ import annotations

import asyncio
from typing import Any

from crxzipple.modules.tool.domain import Tool, ToolExecutionContext
from crxzipple.modules.tool.domain.exceptions import ToolExecutionNotSupportedError
from crxzipple.modules.tool.infrastructure.runtimes.registry import ToolRuntimeRegistry
from crxzipple.modules.tool.infrastructure.runtimes.sandbox_backends import SandboxBackend


class SandboxAsyncToolExecutor:
    def __init__(
        self,
        registry: ToolRuntimeRegistry,
        backend: SandboxBackend,
    ) -> None:
        self.registry = registry
        self.backend = backend

    async def execute_async(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> Any:
        runtime_key = tool.resolved_runtime_key()
        if self.registry.get_handler(runtime_key) is None:
            raise ToolExecutionNotSupportedError(
                f"No sandbox async handler is registered for tool '{tool.id}'.",
            )
        return await asyncio.to_thread(
            self.backend.execute,
            runtime_key,
            tool.execution_policy.timeout_seconds,
            dict(arguments),
            execution_context,
        )
