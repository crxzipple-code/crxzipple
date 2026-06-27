from __future__ import annotations

from typing import Any

from crxzipple.core.config import McpProviderSettings
from .mcp_protocol import require_tools_payload
from .mcp_stdio_async_session import McpStdioAsyncSession
from .mcp_stdio_sync_session import McpStdioSyncSession


class McpStdioClient:
    def __init__(self, config: McpProviderSettings) -> None:
        self.config = config
        self._sync_session = McpStdioSyncSession(config)
        self._async_session = McpStdioAsyncSession(config)

    def list_tools(self) -> list[dict[str, Any]]:
        result = self.request("tools/list")
        return require_tools_payload(result, provider_name=self.config.name)

    def call_tool(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        return self.request(
            "tools/call",
            {
                "name": tool_name,
                "arguments": dict(arguments),
            },
        )

    async def call_tool_async(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        return await self.request_async(
            "tools/call",
            {
                "name": tool_name,
                "arguments": dict(arguments),
            },
        )

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._sync_session.request(method, params)

    async def request_async(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._async_session.request(method, params)

    def close(self) -> None:
        self._sync_session.close()
        self._async_session.close()


__all__ = ["McpStdioClient"]
