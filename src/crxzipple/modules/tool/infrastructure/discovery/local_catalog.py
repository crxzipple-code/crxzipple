from __future__ import annotations

from collections.abc import Callable
import threading
from typing import Any

from crxzipple.modules.tool.domain import Tool


LocalToolHandler = Callable[..., Any]


class LocalToolCatalog:
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
        provider_name: str = "local_builtin",
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

    def replace_provider_tools(
        self,
        provider_name: str,
        entries: list[tuple[Tool, LocalToolHandler]],
    ) -> None:
        with self._lock:
            for tool_id in [
                existing_tool_id
                for existing_tool_id, existing_provider_name in self._provider_names_by_tool_id.items()
                if existing_provider_name == provider_name
            ]:
                self._remove(tool_id)
            for tool, handler in entries:
                self.register(tool, handler, provider_name=provider_name)

    def list_local_tools(self, *, provider_name: str | None = None) -> list[Tool]:
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

    def _remove(self, tool_id: str) -> None:
        runtime_key = self._runtime_keys_by_tool_id.pop(tool_id, None)
        if runtime_key is not None:
            self._handlers.pop(runtime_key, None)
        self._tools.pop(tool_id, None)
        self._provider_names_by_tool_id.pop(tool_id, None)
