from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from crxzipple.modules.orchestration.application.ports import (
    ToolCatalogPort,
    ToolExecutionPort,
)
from crxzipple.modules.tool.application import ExecuteToolInput


@dataclass(slots=True)
class ToolServiceAdapter(ToolCatalogPort, ToolExecutionPort):
    service: Any

    def list_enabled_tools(self, *, runtime_context: Mapping[str, Any] | None = None):
        return self.service.list_enabled_tools(runtime_context=runtime_context)

    async def execute(self, data: ExecuteToolInput):
        return await self.service.execute(data)

    async def execute_many(self, items: tuple[ExecuteToolInput, ...]):
        return await self.service.execute_many(items)

    def get_tool_run(self, run_id: str):
        return self.service.get_tool_run(run_id)

    def cancel_tool_run(self, run_id: str):
        return self.service.cancel_tool_run(run_id)
