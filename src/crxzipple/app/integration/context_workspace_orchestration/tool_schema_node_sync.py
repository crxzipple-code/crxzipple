"""Context Tree node synchronization for requested tool schemas."""

from __future__ import annotations

from crxzipple.modules.context_workspace.application import (
    ContextActionInput,
    ContextTreeService,
)
from crxzipple.modules.context_workspace.domain import ContextAction

from .tool_schema_node_expansion import (
    expand_tool_schema_parent_nodes,
)
from .tool_schema_node_values import (
    tool_function_nodes_include,
    tool_node_function_name,
)


def sync_requested_tool_schema_nodes(
    *,
    tree_service: ContextTreeService | None,
    session_key: str,
    run_id: str,
    schema_names: tuple[str, ...],
    render_metadata: dict[str, object],
) -> None:
    if tree_service is None:
        return
    requested_names = frozenset(
        name.strip()
        for name in schema_names
        if isinstance(name, str) and name.strip()
    )
    if not requested_names:
        return
    function_nodes = tree_service.list_tool_nodes_by_kind(
        session_key,
        kinds=("tool_function",),
    )
    if not tool_function_nodes_include(function_nodes, schema_names=requested_names):
        expand_tool_schema_parent_nodes(
            tree_service=tree_service,
            session_key=session_key,
            run_id=run_id,
            schema_names=requested_names,
            render_metadata=render_metadata,
        )
        function_nodes = tree_service.list_tool_nodes_by_kind(
            session_key,
            kinds=("tool_function",),
        )
    for node in function_nodes:
        name = tool_node_function_name(node)
        if name not in requested_names:
            continue
        if node.state.schema_enabled or not node.supports(
            ContextAction.ENABLE_TOOL_SCHEMA,
        ):
            continue
        tree_service.apply_action(
            ContextActionInput(
                session_key=session_key,
                run_id=run_id,
                node_id=node.id,
                action=ContextAction.ENABLE_TOOL_SCHEMA,
            ),
        )
