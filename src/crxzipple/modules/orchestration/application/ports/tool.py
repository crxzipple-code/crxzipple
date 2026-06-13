from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from crxzipple.modules.tool.application import ExecuteToolInput
from crxzipple.modules.tool.domain import Tool, ToolRun


class ToolCatalogPort(Protocol):
    def list_enabled_tools(
        self,
        *,
        runtime_context: Mapping[str, Any] | None = None,
    ) -> list[Tool]:
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


class ToolSurfacePort(Protocol):
    def build_tool_surface(
        self,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        agent_id: str | None = None,
        runtime_context: object | None = None,
        surface_id: str | None = None,
        tool_ids: tuple[str, ...] | None = None,
        persist: bool = False,
    ) -> object:
        ...
