from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from crxzipple.modules.tool.application.runtime_pool_service import (
    ToolRuntimePoolContext,
    ToolRuntimePoolService,
)
from crxzipple.modules.tool.application.service_support import ToolServiceBase
from crxzipple.modules.tool.application.surface_models import (
    ToolSurface,
    ToolSurfaceFunction,
    ToolSurfaceGroup,
    ToolSurfaceSource,
)
from crxzipple.modules.tool.application.surface_projection import (
    group_key_for_function,
    surface_function,
    surface_source,
)
from crxzipple.modules.tool.domain.value_objects import (
    ToolSourceStatus,
)

__all__ = [
    "ToolSurface",
    "ToolSurfaceFunction",
    "ToolSurfaceGroup",
    "ToolSurfaceQueryService",
    "ToolSurfaceSource",
]


class ToolSurfaceQueryService(ToolServiceBase):
    def __init__(
        self,
        deps,
        *,
        runtime_pool_service: ToolRuntimePoolService,
    ) -> None:
        super().__init__(deps)
        self._runtime_pool_service = runtime_pool_service

    def build_surface(
        self,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        agent_id: str | None = None,
        runtime_context: ToolRuntimePoolContext | Mapping[str, Any] | None = None,
        surface_id: str | None = None,
        tool_ids: tuple[str, ...] | None = None,
        persist: bool = False,
    ) -> ToolSurface:
        context = _surface_runtime_context(
            runtime_context,
            agent_id=agent_id,
            session_id=session_id,
            run_id=run_id,
        )
        pool = self._runtime_pool_service.build_pool(runtime_context=context)
        requested_tool_ids = _normalized_tool_ids(tool_ids)
        tools_by_id = {
            tool.id: tool
            for tool in pool.enabled_tools
            if requested_tool_ids is None or tool.id in requested_tool_ids
        }
        with self.uow_factory() as uow:
            functions = uow.tool_functions.list_by_ids(tuple(tools_by_id))
            sources = uow.tool_sources.list_by_ids(
                tuple(
                    dict.fromkeys(
                        function.source_id
                        for function in functions.values()
                    ),
                ),
            )

        functions_by_source: dict[str, list[ToolSurfaceFunction]] = {}
        for tool_id, tool in sorted(tools_by_id.items()):
            function = functions.get(tool_id)
            if function is None:
                continue
            group_key = group_key_for_function(
                function,
                source=sources.get(function.source_id),
            )
            projected = surface_function(tool, function, group_key=group_key)
            functions_by_source.setdefault(function.source_id, []).append(projected)

        sources_payload: list[ToolSurfaceSource] = []
        for source_id in sorted(functions_by_source):
            source = sources.get(source_id)
            if source is None or source.status is not ToolSourceStatus.ACTIVE:
                continue
            source_functions = tuple(functions_by_source[source_id])
            sources_payload.append(
                surface_source(
                    source,
                    functions=source_functions,
                ),
            )

        functions_payload = tuple(
            function
            for source in sources_payload
            for function in functions_by_source.get(source.source_id, ())
        )
        surface = ToolSurface(
            surface_id=surface_id or f"tool_surface:{uuid4().hex}",
            session_id=_optional_text(session_id),
            run_id=_optional_text(run_id),
            agent_id=_optional_text(agent_id),
            sources=tuple(sources_payload),
            functions=functions_payload,
            parallel_tool_calls=all(function.supports_parallel for function in functions_payload),
            estimate={
                "source_count": len(sources_payload),
                "group_count": sum(len(source.groups) for source in sources_payload),
                "function_count": len(functions_payload),
            },
            diagnostics={
                "excluded_count": len(pool.excluded),
                "requested_tool_count": (
                    len(requested_tool_ids) if requested_tool_ids is not None else None
                ),
                "excluded": [
                    {
                        "tool_id": exclusion.tool_id,
                        "category": exclusion.category,
                        "status": exclusion.status,
                        "reason": exclusion.reason,
                    }
                    for exclusion in pool.excluded
                ],
            },
        )
        if persist:
            with self.uow_factory() as uow:
                uow.tool_surfaces.add(surface)
                uow.commit()
        return surface


def _normalized_tool_ids(tool_ids: tuple[str, ...] | None) -> frozenset[str] | None:
    if tool_ids is None:
        return None
    return frozenset(tool_id.strip() for tool_id in tool_ids if tool_id.strip())


def _surface_runtime_context(
    runtime_context: ToolRuntimePoolContext | Mapping[str, Any] | None,
    *,
    agent_id: str | None,
    session_id: str | None,
    run_id: str | None,
) -> ToolRuntimePoolContext:
    if isinstance(runtime_context, ToolRuntimePoolContext):
        base = dict(runtime_context.attrs)
        if session_id is not None:
            base.setdefault("session_id", session_id)
        if run_id is not None:
            base.setdefault("run_id", run_id)
        return ToolRuntimePoolContext(
            caller=runtime_context.caller,
            agent_id=runtime_context.agent_id or _optional_text(agent_id),
            session_key=runtime_context.session_key,
            workspace_dir=runtime_context.workspace_dir,
            attrs=base,
        )
    payload = dict(runtime_context or {})
    payload.setdefault("caller", "orchestration")
    if agent_id is not None:
        payload.setdefault("agent_id", agent_id)
    if session_id is not None:
        payload.setdefault("session_id", session_id)
    if run_id is not None:
        payload.setdefault("run_id", run_id)
    return ToolRuntimePoolContext.from_mapping(payload)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
