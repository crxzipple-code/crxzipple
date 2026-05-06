from __future__ import annotations

import asyncio
import time
from typing import Any
from weakref import WeakKeyDictionary

from crxzipple.modules.tool.domain import Tool, ToolExecutionContext
from crxzipple.modules.tool.domain.exceptions import ToolExecutionNotSupportedError
from crxzipple.modules.tool.infrastructure.handler_invocation import (
    invoke_tool_handler,
)
from crxzipple.modules.tool.infrastructure.runtimes.registry import (
    ToolRuntimeRegistration,
    ToolRuntimeRegistry,
)
from crxzipple.shared.runtime_metrics import (
    RuntimeMetricsRegistry,
    get_runtime_metrics_registry,
)


class RemoteAsyncToolExecutor:
    def __init__(
        self,
        registry: ToolRuntimeRegistry,
        *,
        metrics: RuntimeMetricsRegistry | None = None,
    ) -> None:
        self.registry = registry
        self.metrics = metrics or get_runtime_metrics_registry()
        self._semaphores: WeakKeyDictionary[
            asyncio.AbstractEventLoop,
            dict[str, tuple[int, asyncio.Semaphore]],
        ] = WeakKeyDictionary()

    async def execute_async(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> Any:
        runtime_key = tool.resolved_runtime_key()
        registration = self.registry.get_registration(runtime_key)
        if registration is None:
            raise ToolExecutionNotSupportedError(
                f"No remote async handler is registered for tool '{tool.id}'.",
            )
        limiter = self._get_limiter(registration, runtime_key=runtime_key)
        if limiter is None:
            return await invoke_tool_handler(
                registration.handler,
                arguments,
                execution_context,
            )
        semaphore, concurrency_key = limiter
        labels = {"provider_key": concurrency_key}
        wait_started_at = time.perf_counter()
        with self.metrics.active(
            "tool.remote_provider_limiter.waiters",
            labels=labels,
        ):
            await semaphore.acquire()
        self.metrics.record_timing(
            "tool.remote_provider_limiter.wait_seconds",
            time.perf_counter() - wait_started_at,
            labels=labels,
        )
        try:
            with self.metrics.active(
                "tool.remote_provider_limiter.active",
                labels=labels,
            ):
                return await invoke_tool_handler(
                    registration.handler,
                    arguments,
                    execution_context,
                )
        finally:
            semaphore.release()

    def _get_limiter(
        self,
        registration: ToolRuntimeRegistration,
        *,
        runtime_key: str,
    ) -> tuple[asyncio.Semaphore, str] | None:
        max_concurrency = registration.max_concurrency
        if max_concurrency is None:
            return None

        loop = asyncio.get_running_loop()
        semaphores_by_key = self._semaphores.setdefault(loop, {})
        concurrency_key = registration.concurrency_key or runtime_key
        stored = semaphores_by_key.get(concurrency_key)
        if stored is not None and stored[0] == max_concurrency:
            return stored[1], concurrency_key

        semaphore = asyncio.Semaphore(max_concurrency)
        semaphores_by_key[concurrency_key] = (max_concurrency, semaphore)
        return semaphore, concurrency_key
