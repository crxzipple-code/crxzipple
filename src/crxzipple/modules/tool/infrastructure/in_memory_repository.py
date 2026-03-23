from __future__ import annotations

from crxzipple.modules.tool.domain.entities import Tool, ToolRun


class InMemoryToolRepository:
    def __init__(self) -> None:
        self._items: dict[str, Tool] = {}

    def add(self, tool: Tool) -> None:
        self._items[tool.id] = tool

    def get(self, tool_id: str) -> Tool | None:
        return self._items.get(tool_id)

    def list(self) -> list[Tool]:
        return list(self._items.values())

    def list_enabled(self) -> list[Tool]:
        return [tool for tool in self._items.values() if tool.enabled]


class InMemoryToolRunRepository:
    def __init__(self) -> None:
        self._items: dict[str, ToolRun] = {}

    def add(self, tool_run: ToolRun) -> None:
        self._items[tool_run.id] = tool_run

    def get(self, run_id: str) -> ToolRun | None:
        return self._items.get(run_id)

    def list(self) -> list[ToolRun]:
        return list(self._items.values())

    def list_for_tool(self, tool_id: str) -> list[ToolRun]:
        return [run for run in self._items.values() if run.tool_id == tool_id]
