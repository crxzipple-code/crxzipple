from __future__ import annotations

from crxzipple.modules.context_workspace.application.models import ContextSliceToolRef
from crxzipple.modules.context_workspace.domain import ContextNode


def active_tools_for_slice(
    *,
    nodes: tuple[ContextNode, ...],
    audience: str,
    requested_tool_schema_names: frozenset[str] = frozenset(),
) -> tuple[ContextSliceToolRef, ...]:
    if not _include_active_tools(audience):
        return ()
    return tuple(
        tool_ref
        for node in nodes
        for tool_ref in (
            context_slice_tool_ref(
                node,
                requested_tool_schema_names=requested_tool_schema_names,
            ),
        )
        if tool_ref is not None
    )


def context_slice_tool_ref(
    node: ContextNode,
    *,
    requested_tool_schema_names: frozenset[str] = frozenset(),
) -> ContextSliceToolRef | None:
    if node.owner != "tool" or node.kind != "tool_function":
        return None
    function_name = tool_function_name(node)
    if not isinstance(function_name, str) or not function_name.strip():
        return None
    function_name = function_name.strip()
    if not (
        node.state.schema_enabled
        or node.state.included_in_next_tool_surface
        or function_name in requested_tool_schema_names
    ):
        return None
    source_id = _metadata_text(node.owner_ref.get("source_id")) or ""
    return ContextSliceToolRef(
        tool_ref_id=node.id,
        node_id=node.id,
        source_id=source_id,
        function_name=function_name,
        owner_ref=dict(node.owner_ref),
        metadata={
            "status": node.state.status,
            "render_priority": node.state.render_priority,
        },
    )


def tool_function_name(node: ContextNode) -> str | None:
    for value in (
        node.owner_ref.get("tool_id"),
        node.owner_ref.get("function_id"),
        node.metadata.get("function_name"),
    ):
        text = _metadata_text(value)
        if text is not None:
            return text
    return None


def _include_active_tools(audience: str) -> bool:
    return audience in {"llm_request", "trace_timeline", "operations_projection"}


def _metadata_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


__all__ = [
    "active_tools_for_slice",
    "context_slice_tool_ref",
    "tool_function_name",
]
