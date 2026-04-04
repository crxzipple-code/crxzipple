from __future__ import annotations

from crxzipple.modules.tool.domain.entities import ToolRun


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
