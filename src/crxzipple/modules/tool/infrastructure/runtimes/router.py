from __future__ import annotations

from typing import Any

from crxzipple.modules.tool.domain import (
    Tool,
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolExecutionTarget,
)
from crxzipple.modules.tool.domain.exceptions import ToolExecutionNotSupportedError
from crxzipple.modules.tool.infrastructure.executors import LocalAsyncToolExecutor
from crxzipple.modules.tool.infrastructure.runtimes.remote import RemoteAsyncToolExecutor
from crxzipple.modules.tool.infrastructure.runtimes.sandbox import SandboxAsyncToolExecutor


class ToolRuntimeRouter:
    def __init__(
        self,
        local_executor: LocalAsyncToolExecutor,
        sandbox_executor: SandboxAsyncToolExecutor,
        remote_executor: RemoteAsyncToolExecutor,
    ) -> None:
        self.local_executor = local_executor
        self.sandbox_executor = sandbox_executor
        self.remote_executor = remote_executor

    def list_local_tools(self) -> list[Tool]:
        return self.local_executor.list_local_tools()

    async def execute(
        self,
        tool: Tool,
        target: ToolExecutionTarget,
        arguments: dict[str, Any],
    ) -> Any:
        if target.environment is ToolEnvironment.LOCAL:
            if target.strategy is ToolExecutionStrategy.ASYNC:
                return await self.local_executor.execute_async(tool, arguments)
            if target.strategy is ToolExecutionStrategy.THREAD:
                return await self.local_executor.execute_thread(tool, arguments)
            if target.strategy is ToolExecutionStrategy.PROCESS:
                return await self.local_executor.execute_process(tool, arguments)
            raise ToolExecutionNotSupportedError(
                f"Unsupported local execution strategy '{target.strategy.value}'.",
            )

        if target.strategy is not ToolExecutionStrategy.ASYNC:
            raise ToolExecutionNotSupportedError(
                f"{target.environment.value} runtime currently supports only async strategy; received '{target.strategy.value}'.",
            )

        if target.environment is ToolEnvironment.SANDBOX:
            return await self.sandbox_executor.execute_async(tool, arguments)
        if target.environment is ToolEnvironment.REMOTE:
            return await self.remote_executor.execute_async(tool, arguments)

        raise ToolExecutionNotSupportedError(
            f"Unsupported runtime environment '{target.environment.value}'.",
        )
