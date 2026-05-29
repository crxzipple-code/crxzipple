from __future__ import annotations

from crxzipple.modules.tool.application.service_support import (
    ToolServiceBase,
    ToolServiceDependencies,
    build_tool_from_function,
)
from crxzipple.modules.tool.domain.entities import Tool
from crxzipple.modules.tool.domain.exceptions import ToolNotFoundError
from crxzipple.modules.tool.domain.value_objects import (
    ToolFunctionStatus,
    ToolSourceStatus,
)

_CATALOG_TOOL_UNAVAILABLE = object()


class ToolCatalogService(ToolServiceBase):
    def __init__(self, deps: ToolServiceDependencies) -> None:
        super().__init__(deps)

    def list_tools(self) -> list[Tool]:
        resolved = self._catalog_tool_map()
        return [resolved[tool_id] for tool_id in sorted(resolved)]

    def list_enabled_tools(self) -> list[Tool]:
        resolved = {
            tool.id: tool
            for tool in self.list_tools()
        }
        return [
            resolved[tool_id]
            for tool_id in sorted(resolved)
            if resolved[tool_id].enabled
        ]

    def get_tool(self, tool_id: str) -> Tool:
        tool = self.resolve_tool(tool_id)
        if tool is None:
            raise ToolNotFoundError(f"Tool '{tool_id}' was not found.")
        return tool

    def resolved_tool_map(self) -> dict[str, Tool]:
        return self._catalog_tool_map()

    def resolve_tool(self, tool_id: str) -> Tool | None:
        catalog_tool = self._catalog_tool(tool_id)
        if catalog_tool is _CATALOG_TOOL_UNAVAILABLE:
            return None
        if isinstance(catalog_tool, Tool):
            return catalog_tool
        return None

    def _catalog_tool_map(self) -> dict[str, Tool]:
        with self.uow_factory() as uow:
            functions = uow.tool_functions.list(status=ToolFunctionStatus.ACTIVE)
            source_ids = tuple(dict.fromkeys(function.source_id for function in functions))
            sources = {
                source_id: uow.tool_sources.get(source_id)
                for source_id in source_ids
            }
        resolved: dict[str, Tool] = {}
        for function in functions:
            source = sources.get(function.source_id)
            if source is None or source.status is not ToolSourceStatus.ACTIVE:
                continue
            resolved[function.function_id] = build_tool_from_function(function)
        return resolved

    def _catalog_tool(self, tool_id: str) -> Tool | object | None:
        with self.uow_factory() as uow:
            function = uow.tool_functions.get(tool_id)
            if function is None:
                return None
            source = uow.tool_sources.get(function.source_id)
        if (
            source is None
            or source.status is not ToolSourceStatus.ACTIVE
            or function.status is not ToolFunctionStatus.ACTIVE
        ):
            return _CATALOG_TOOL_UNAVAILABLE
        return build_tool_from_function(function)
