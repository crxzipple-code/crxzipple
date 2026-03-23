from __future__ import annotations

import asyncio
from typing import Any

from crxzipple.modules.tool.domain import ToolRunResult
from crxzipple.modules.tool.infrastructure.discovery.mcp import McpToolDefinition
from crxzipple.modules.tool.infrastructure.mcp_client import McpStdioClient
from crxzipple.modules.tool.infrastructure.runtimes.registry import ToolRuntimeRegistry


class McpRemoteInvoker:
    def __init__(self, client: McpStdioClient) -> None:
        self.client = client

    async def execute(
        self,
        definition: McpToolDefinition,
        arguments: dict[str, Any],
    ) -> Any:
        result = await asyncio.to_thread(
            self.client.call_tool,
            tool_name=definition.tool_name,
            arguments=dict(arguments),
        )
        return ToolRunResult(
            content=result,
            metadata={
                "tool": definition.runtime_key,
                "environment": "remote",
                "provider": definition.provider_name,
            },
        )


def register_mcp_remote_handlers(
    registry: ToolRuntimeRegistry,
    definitions: list[McpToolDefinition] | tuple[McpToolDefinition, ...],
    *,
    client: McpStdioClient,
) -> None:
    invoker = McpRemoteInvoker(client)
    for definition in definitions:

        async def handler(
            arguments: dict[str, Any],
            *,
            _definition: McpToolDefinition = definition,
            _invoker: McpRemoteInvoker = invoker,
        ) -> Any:
            return await _invoker.execute(_definition, arguments)

        registry.register(definition.runtime_key, handler)
