from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.orchestration.application.ports import (
    ToolCatalogPort,
    ToolExecutionPort,
)
from crxzipple.modules.tool.application import ExecuteToolInput, ToolApplicationService


@dataclass(slots=True)
class ToolServiceAdapter(ToolCatalogPort, ToolExecutionPort):
    service: ToolApplicationService

    def ensure_local_system_tools_registered(self):
        return self.service.ensure_local_system_tools_registered()

    def list_enabled_tools(self):
        return self.service.list_enabled_tools()

    async def execute(self, data: ExecuteToolInput):
        return await self.service.execute(data)

    async def execute_many(self, items: tuple[ExecuteToolInput, ...]):
        return await self.service.execute_many(items)

    def get_tool_run(self, run_id: str):
        return self.service.get_tool_run(run_id)

    def cancel_tool_run(self, run_id: str):
        return self.service.cancel_tool_run(run_id)
