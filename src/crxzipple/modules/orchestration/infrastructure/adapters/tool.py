from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from crxzipple.modules.orchestration.application.ports import (
    ToolCatalogPort,
    ToolExecutionPort,
    ToolSurfacePort,
)
from crxzipple.modules.tool.application import ExecuteToolInput


@dataclass(slots=True)
class ToolServiceAdapter(ToolCatalogPort, ToolExecutionPort, ToolSurfacePort):
    service: Any

    def list_enabled_tools(self, *, runtime_context: Mapping[str, Any] | None = None):
        return self.service.list_enabled_tools(runtime_context=runtime_context)

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
    ):
        return self.service.build_tool_surface(
            session_id=session_id,
            run_id=run_id,
            agent_id=agent_id,
            runtime_context=runtime_context,
            surface_id=surface_id,
            tool_ids=tool_ids,
            persist=persist,
        )

    async def execute(self, data: ExecuteToolInput):
        return await self.service.execute(data)

    async def execute_many(self, items: tuple[ExecuteToolInput, ...]):
        return await self.service.execute_many(items)

    def get_tool_run(self, run_id: str):
        return self.service.get_tool_run(run_id)

    def cancel_tool_run(self, run_id: str):
        return self.service.cancel_tool_run(run_id)
