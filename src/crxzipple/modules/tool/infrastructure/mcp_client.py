from __future__ import annotations

from typing import Any, Protocol

from crxzipple.core.config import McpProviderSettings
from .mcp_http_client import McpHttpClient
from .mcp_stdio_client import McpStdioClient


class McpClient(Protocol):
    def list_tools(self) -> list[dict[str, Any]]:
        ...

    def call_tool(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        ...

    async def call_tool_async(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        ...

    def close(self) -> None:
        ...


def build_mcp_client(config: McpProviderSettings) -> McpClient:
    if config.transport == "http":
        return McpHttpClient(config)
    return McpStdioClient(config)


__all__ = ["McpClient", "McpHttpClient", "McpStdioClient", "build_mcp_client"]
