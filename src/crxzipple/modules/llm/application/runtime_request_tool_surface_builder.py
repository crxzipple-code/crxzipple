from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from crxzipple.modules.llm.application.runtime_tool_surface import (
    RuntimeToolSurface,
    RuntimeToolSurfaceRef,
    tool_schemas_from_projected_refs,
)
from crxzipple.modules.llm.domain import ToolSchema

if TYPE_CHECKING:
    from crxzipple.modules.orchestration.application.ports import (
        RequestRenderSnapshotRecord,
    )
    from crxzipple.modules.orchestration.application.tool_resolver import ResolvedToolSet
else:
    RequestRenderSnapshotRecord = Any
    ResolvedToolSet = Any


def tool_schemas_from_request_render_snapshot(
    snapshot: RequestRenderSnapshotRecord | None,
) -> tuple[ToolSchema, ...]:
    if snapshot is None:
        return ()
    return tool_schemas_from_projected_refs(
        tuple(raw for raw in snapshot.tool_schema_refs if isinstance(raw, Mapping)),
    )


def tool_surface_from_resolved_tools(
    resolved_tools: ResolvedToolSet,
    *,
    tool_schemas: tuple[ToolSchema, ...],
    request_render_snapshot: RequestRenderSnapshotRecord | None,
) -> RuntimeToolSurface:
    snapshot_id = (
        request_render_snapshot.snapshot_id
        if request_render_snapshot is not None
        else "none"
    )
    schema_names = tuple(schema.name for schema in tool_schemas)
    schema_ref_by_name = _tool_schema_ref_by_name(request_render_snapshot)
    functions: list[RuntimeToolSurfaceRef] = []
    for item in resolved_tools.tools:
        schema_ref = schema_ref_by_name.get(item.schema.name, {})
        functions.append(
            RuntimeToolSurfaceRef(
                tool_id=item.tool.id,
                name=item.schema.name,
                schema=item.schema,
                target=_tool_target_label(item.target),
                source_id=_tool_schema_ref_text(schema_ref, "source_id"),
                group_key=_tool_schema_ref_text(schema_ref, "group_key"),
                always_visible=item.schema.name in schema_names,
                enabled=True,
                metadata=_tool_surface_ref_metadata(schema_ref),
            ),
        )
    return RuntimeToolSurface(
        id=f"tool_surface:{snapshot_id}",
        functions=tuple(functions),
        mirrored_schema_names=schema_names,
        blocked_access_count=len(resolved_tools.blocked_access),
        metadata={
            "request_render_snapshot_id": (
                request_render_snapshot.snapshot_id
                if request_render_snapshot is not None
                else None
            ),
            "tool_schema_count": len(schema_names),
            "mirrored_schema_name_count": len(schema_names),
            "function_count": len(functions),
        },
    )


def _tool_schema_ref_by_name(
    snapshot: RequestRenderSnapshotRecord | None,
) -> dict[str, dict[str, object]]:
    if snapshot is None:
        return {}
    refs: dict[str, dict[str, object]] = {}
    for raw_ref in snapshot.tool_schema_refs:
        if not isinstance(raw_ref, Mapping):
            continue
        name = _tool_schema_ref_text(raw_ref, "name", "function_name")
        if name is None or name in refs:
            continue
        refs[name] = dict(raw_ref)
    return refs


def _tool_surface_ref_metadata(ref: Mapping[str, object]) -> dict[str, object]:
    metadata: dict[str, object] = {}
    for key in (
        "source",
        "node_id",
        "tool_ref_id",
    ):
        value = _tool_schema_ref_text(ref, key)
        if value is not None:
            metadata[key] = value
    function_name = _tool_schema_ref_text(ref, "function_name", "name")
    if function_name is not None:
        metadata["function_name"] = function_name
    return metadata


def _tool_schema_ref_text(
    ref: Mapping[str, object],
    *keys: str,
) -> str | None:
    for key in keys:
        value = ref.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _tool_target_label(target: object) -> str:
    mode = getattr(target, "mode", None)
    strategy = getattr(target, "strategy", None)
    environment = getattr(target, "environment", None)
    parts = []
    for value in (mode, strategy, environment):
        if value is None:
            continue
        parts.append(str(getattr(value, "value", value)))
    return ":".join(parts) or "unknown"


__all__ = [
    "tool_schemas_from_request_render_snapshot",
    "tool_surface_from_resolved_tools",
]
