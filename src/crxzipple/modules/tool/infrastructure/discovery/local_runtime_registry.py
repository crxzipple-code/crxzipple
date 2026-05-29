from __future__ import annotations

from collections.abc import Callable
import threading
from typing import Any

from crxzipple.modules.tool.domain import Tool


LocalToolHandler = Callable[..., Any]


class LocalToolRuntimeRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._handlers: dict[str, LocalToolHandler] = {}
        self._provider_names_by_tool_id: dict[str, str] = {}
        self._runtime_keys_by_tool_id: dict[str, str] = {}
        self._lock = threading.RLock()

    def register(
        self,
        tool: Tool,
        handler: LocalToolHandler,
        *,
        provider_name: str = "local_system",
    ) -> None:
        with self._lock:
            runtime_key = tool.resolved_runtime_key()
            previous_runtime_key = self._runtime_keys_by_tool_id.get(tool.id)
            if previous_runtime_key is not None and previous_runtime_key != runtime_key:
                self._handlers.pop(previous_runtime_key, None)
            self._tools[tool.id] = tool
            self._handlers[runtime_key] = handler
            self._provider_names_by_tool_id[tool.id] = provider_name
            self._runtime_keys_by_tool_id[tool.id] = runtime_key

    def list_registered_tools(self, *, provider_name: str | None = None) -> list[Tool]:
        with self._lock:
            if provider_name is None:
                return list(self._tools.values())
            return [
                tool
                for tool_id, tool in self._tools.items()
                if self._provider_names_by_tool_id.get(tool_id) == provider_name
            ]

    def get_handler(self, runtime_key: str) -> LocalToolHandler | None:
        with self._lock:
            return self._handlers.get(runtime_key)
