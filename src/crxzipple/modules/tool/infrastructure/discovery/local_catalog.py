from __future__ import annotations

from collections.abc import Callable
import os
import threading
from typing import Any

from crxzipple.modules.tool.domain import (
    Tool,
    ToolEnvironment,
    ToolExecutionSupport,
    ToolExecutionStrategy,
    ToolKind,
    ToolMode,
    ToolParameter,
    ToolRunResult,
    ToolSourceKind,
)


LocalToolHandler = Callable[[dict[str, Any]], Any]


class LocalToolCatalog:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._handlers: dict[str, LocalToolHandler] = {}
        self._provider_names_by_tool_id: dict[str, str] = {}

    def register(
        self,
        tool: Tool,
        handler: LocalToolHandler,
        *,
        provider_name: str = "local_builtin",
    ) -> None:
        runtime_key = tool.resolved_runtime_key()
        self._tools[tool.id] = tool
        self._handlers[runtime_key] = handler
        self._provider_names_by_tool_id[tool.id] = provider_name

    def list_local_tools(self, *, provider_name: str | None = None) -> list[Tool]:
        if provider_name is None:
            return list(self._tools.values())
        return [
            tool
            for tool_id, tool in self._tools.items()
            if self._provider_names_by_tool_id.get(tool_id) == provider_name
        ]

    def get_handler(self, runtime_key: str) -> LocalToolHandler | None:
        return self._handlers.get(runtime_key)


async def _echo_tool(arguments: dict[str, Any]) -> ToolRunResult:
    return ToolRunResult(
        content={
            "received": dict(arguments),
            "message": arguments.get("message"),
        },
        metadata={
            "tool": "echo",
            "environment": "local",
            "process_id": os.getpid(),
            "thread_name": threading.current_thread().name,
            "thread_ident": threading.get_ident(),
        },
    )


def register_builtin_local_tools(catalog: LocalToolCatalog) -> None:
    catalog.register(
        Tool(
            id="echo",
            name="Echo",
            description="Returns the input payload for local inline execution tests.",
            kind=ToolKind.FUNCTION,
            parameters=(
                ToolParameter(
                    name="message",
                    data_type="string",
                    description="Text to echo back.",
                    required=False,
                ),
            ),
            tags=("local", "builtin", "debug"),
            execution_support=ToolExecutionSupport(
                supported_modes=(ToolMode.INLINE, ToolMode.BACKGROUND),
                supported_strategies=(
                    ToolExecutionStrategy.ASYNC,
                    ToolExecutionStrategy.THREAD,
                    ToolExecutionStrategy.PROCESS,
                ),
                supported_environments=(ToolEnvironment.LOCAL,),
            ),
            source_kind=ToolSourceKind.LOCAL_DISCOVERY,
            runtime_key="echo",
            enabled=True,
        ),
        _echo_tool,
        provider_name="local_builtin",
    )
