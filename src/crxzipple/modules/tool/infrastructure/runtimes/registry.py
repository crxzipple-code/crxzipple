from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


AsyncToolHandler = Callable[[dict[str, Any]], Awaitable[Any]]


class ToolRuntimeRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, AsyncToolHandler] = {}

    def register(self, runtime_key: str, handler: AsyncToolHandler) -> None:
        self._handlers[runtime_key] = handler

    def get_handler(self, runtime_key: str) -> AsyncToolHandler | None:
        return self._handlers.get(runtime_key)

    def count(self) -> int:
        return len(self._handlers)
