from __future__ import annotations

from crxzipple.modules.tool.application.catalog_service import ToolCatalogService
from crxzipple.modules.tool.application.service_support import build_tool_from_function
from crxzipple.modules.tool.domain.entities import Tool, ToolRun
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.domain.value_objects import (
    ToolFunctionStatus,
    ToolSourceStatus,
)


def resolve_run_tool_for_concurrency(
    uow,
    run: ToolRun,
    *,
    catalog_service: ToolCatalogService,
) -> Tool | None:
    if run.function_id is not None:
        function = uow.tool_functions.get(run.function_id)
        if function is not None:
            return build_tool_from_function(function)
    return catalog_service.resolve_tool(run.tool_id)


def resolve_run_catalog_tool(uow, run: ToolRun) -> Tool | None:
    if run.function_id is None:
        return None
    function = uow.tool_functions.get(run.function_id)
    if function is None:
        raise ToolValidationError(
            f"Tool run '{run.id}' references missing function '{run.function_id}'.",
        )
    source = uow.tool_sources.get(function.source_id)
    if source is None:
        raise ToolValidationError(
            f"Tool run '{run.id}' references missing source '{function.source_id}'.",
        )
    if source.status is not ToolSourceStatus.ACTIVE:
        raise ToolValidationError(
            f"Tool source '{source.source_id}' is {source.status.value}.",
        )
    if function.status is not ToolFunctionStatus.ACTIVE:
        raise ToolValidationError(
            f"Tool function '{function.function_id}' is {function.status.value}.",
        )
    if not function.enabled:
        raise ToolValidationError(
            f"Tool function '{function.function_id}' is disabled.",
        )
    return build_tool_from_function(function)
