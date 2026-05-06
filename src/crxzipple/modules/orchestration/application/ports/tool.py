from __future__ import annotations

from typing import Protocol

from crxzipple.modules.tool.application import ExecuteToolInput
from crxzipple.modules.tool.domain import Tool, ToolRun


class ToolCatalogPort(Protocol):
    def ensure_local_system_tools_registered(self) -> tuple[Tool, ...]:
        ...

    def list_enabled_tools(self) -> list[Tool]:
        ...


class ToolExecutionPort(Protocol):
    async def execute(self, data: ExecuteToolInput) -> ToolRun:
        ...

    async def execute_many(
        self,
        items: tuple[ExecuteToolInput, ...],
    ) -> tuple[ToolRun, ...]:
        ...

    def get_tool_run(self, run_id: str) -> ToolRun:
        ...

    def cancel_tool_run(self, run_id: str) -> ToolRun:
        ...
