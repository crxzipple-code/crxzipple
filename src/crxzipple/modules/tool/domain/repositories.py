from __future__ import annotations

from typing import Protocol

from crxzipple.modules.tool.domain.entities import Tool, ToolRun


class ToolRepository(Protocol):
    def add(self, tool: Tool) -> None:
        ...

    def get(self, tool_id: str) -> Tool | None:
        ...

    def list(self) -> list[Tool]:
        ...

    def list_enabled(self) -> list[Tool]:
        ...


class ToolRunRepository(Protocol):
    def add(self, tool_run: ToolRun) -> None:
        ...

    def get(self, run_id: str) -> ToolRun | None:
        ...

    def list(self) -> list[ToolRun]:
        ...

    def list_for_tool(self, tool_id: str) -> list[ToolRun]:
        ...
