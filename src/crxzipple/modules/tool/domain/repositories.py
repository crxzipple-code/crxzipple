from __future__ import annotations

from typing import Protocol

from crxzipple.modules.tool.domain.entities import ToolRun


class ToolRunRepository(Protocol):
    def add(self, tool_run: ToolRun) -> None:
        ...

    def get(self, run_id: str) -> ToolRun | None:
        ...

    def list(self) -> list[ToolRun]:
        ...

    def list_for_tool(self, tool_id: str) -> list[ToolRun]:
        ...
