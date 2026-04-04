from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from concurrent.futures import ProcessPoolExecutor
import inspect
import multiprocessing
import pickle
from typing import Any

from crxzipple.modules.tool.domain import ToolExecutionContext
from crxzipple.modules.tool.domain import Tool
from crxzipple.modules.tool.domain.exceptions import ToolExecutionNotSupportedError
from crxzipple.modules.tool.infrastructure.discovery import LocalToolCatalog, LocalToolHandler
from crxzipple.modules.tool.infrastructure.handler_invocation import (
    invoke_tool_handler,
)


async def _await_result(result: Awaitable[Any]) -> Any:
    return await result


def _invoke_handler_sync(
    handler: LocalToolHandler,
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None,
) -> Any:
    result = invoke_tool_handler(handler, arguments, execution_context)
    if inspect.isawaitable(result):
        return asyncio.run(_await_result(result))
    return result


class LocalAsyncToolExecutor:
    def __init__(self, catalog: LocalToolCatalog) -> None:
        self.catalog = catalog

    def list_local_tools(self) -> list[Tool]:
        return self.catalog.list_local_tools()

    async def execute_async(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> Any:
        handler = self._resolve_handler(tool, strategy_label="async")
        result = invoke_tool_handler(handler, arguments, execution_context)
        if inspect.isawaitable(result):
            return await result
        return result

    async def execute_thread(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> Any:
        handler = self._resolve_handler(tool, strategy_label="thread")
        return await asyncio.to_thread(
            _invoke_handler_sync,
            handler,
            arguments,
            execution_context,
        )

    async def execute_process(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> Any:
        handler = self._resolve_handler(tool, strategy_label="process")
        loop = asyncio.get_running_loop()
        try:
            with ProcessPoolExecutor(
                max_workers=1,
                mp_context=multiprocessing.get_context("spawn"),
            ) as executor:
                return await loop.run_in_executor(
                    executor,
                    _invoke_handler_sync,
                    handler,
                    arguments,
                    execution_context,
                )
        except (AttributeError, TypeError, pickle.PicklingError) as exc:
            raise ToolExecutionNotSupportedError(
                f"Local process execution could not serialize handler for tool '{tool.id}'.",
            ) from exc

    def _resolve_handler(self, tool: Tool, *, strategy_label: str) -> LocalToolHandler:
        handler = self.catalog.get_handler(tool.resolved_runtime_key())
        if handler is None:
            raise ToolExecutionNotSupportedError(
                f"No local {strategy_label} handler is registered for tool '{tool.id}'.",
            )
        return handler
