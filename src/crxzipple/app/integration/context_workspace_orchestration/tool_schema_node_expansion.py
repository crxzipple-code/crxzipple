"""Context Tree expansion helpers for requested tool schema nodes."""

from __future__ import annotations

from crxzipple.modules.context_workspace.application import (
    ContextActionInput,
    ContextTreeService,
)
from crxzipple.modules.context_workspace.domain import ContextAction

from .request_render_refs import metadata_string_values
from .snapshot_metadata_values import metadata_dict_list
from .tool_schema_node_values import (
    metadata_text_value,
    schema_source_ids,
    tool_function_nodes_include,
)


def expand_tool_schema_parent_nodes(
    *,
    tree_service: ContextTreeService,
    session_key: str,
    run_id: str,
    schema_names: frozenset[str],
    render_metadata: dict[str, object],
) -> None:
    tree_service.list_tree(session_key, refresh=True)
    _expand_context_node_if_present(
        tree_service=tree_service,
        session_key=session_key,
        run_id=run_id,
        node_id="tools.available",
    )
    _expand_tool_groups_from_render_metadata(
        tree_service=tree_service,
        session_key=session_key,
        run_id=run_id,
        render_metadata=render_metadata,
    )
    _expand_tool_groups_for_schema_names(
        tree_service=tree_service,
        session_key=session_key,
        run_id=run_id,
        schema_names=schema_names,
    )


def _expand_tool_groups_from_render_metadata(
    *,
    tree_service: ContextTreeService,
    session_key: str,
    run_id: str,
    render_metadata: dict[str, object],
) -> None:
    bundle_nodes = tree_service.list_tool_nodes_by_kind(
        session_key,
        kinds=("tool_bundle",),
    )
    group_nodes = tree_service.list_tool_nodes_by_kind(
        session_key,
        kinds=("tool_bundle_group",),
    )
    for raw_ref in (
        *metadata_dict_list(render_metadata.get("default_tool_schema_group_matches")),
        *metadata_dict_list(render_metadata.get("default_tool_schema_group_refs")),
    ):
        node_id = metadata_text_value(raw_ref.get("node_id"))
        source_id = metadata_text_value(raw_ref.get("source_id"))
        if source_id is not None:
            bundle_node = next(
                (
                    node
                    for node in bundle_nodes
                    if metadata_text_value(
                        node.owner_ref.get("source_id"),
                        node.metadata.get("source_id"),
                    )
                    == source_id
                ),
                None,
            )
            if bundle_node is not None:
                _expand_context_node_if_present(
                    tree_service=tree_service,
                    session_key=session_key,
                    run_id=run_id,
                    node_id=bundle_node.id,
                )
        if node_id is not None:
            _expand_context_node_if_present(
                tree_service=tree_service,
                session_key=session_key,
                run_id=run_id,
                node_id=node_id,
            )
            continue
        group_key = metadata_text_value(raw_ref.get("group_key"))
        if source_id is None or group_key is None:
            continue
        group_nodes = tree_service.list_tool_nodes_by_kind(
            session_key,
            kinds=("tool_bundle_group",),
        )
        group_node = next(
            (
                node
                for node in group_nodes
                if metadata_text_value(
                    node.owner_ref.get("source_id"),
                    node.metadata.get("source_id"),
                )
                == source_id
                and metadata_text_value(
                    node.owner_ref.get("group_key"),
                    node.metadata.get("group_key"),
                )
                == group_key
            ),
            None,
        )
        if group_node is not None:
            _expand_context_node_if_present(
                tree_service=tree_service,
                session_key=session_key,
                run_id=run_id,
                node_id=group_node.id,
            )


def _expand_tool_groups_for_schema_names(
    *,
    tree_service: ContextTreeService,
    session_key: str,
    run_id: str,
    schema_names: frozenset[str],
) -> None:
    if _tree_tool_function_nodes_include(
        tree_service=tree_service,
        session_key=session_key,
        schema_names=schema_names,
    ):
        return
    source_ids = schema_source_ids(schema_names)
    bundle_nodes = tree_service.list_tool_nodes_by_kind(
        session_key,
        kinds=("tool_bundle",),
    )
    for node in bundle_nodes:
        source_id = metadata_text_value(
            node.owner_ref.get("source_id"),
            node.metadata.get("source_id"),
        )
        if source_ids and source_id not in source_ids:
            continue
        _expand_context_node_if_present(
            tree_service=tree_service,
            session_key=session_key,
            run_id=run_id,
            node_id=node.id,
        )
    group_nodes = tree_service.list_tool_nodes_by_kind(
        session_key,
        kinds=("tool_bundle_group",),
    )
    for node in group_nodes:
        function_names = set(
            metadata_string_values(node.owner_ref.get("function_ids")),
        )
        function_names.update(metadata_string_values(node.metadata.get("function_ids")))
        function_names.update(
            metadata_string_values(node.metadata.get("default_tool_schema_ids")),
        )
        if function_names and schema_names.isdisjoint(function_names):
            continue
        source_id = metadata_text_value(
            node.owner_ref.get("source_id"),
            node.metadata.get("source_id"),
        )
        if not function_names and source_ids and source_id not in source_ids:
            continue
        _expand_context_node_if_present(
            tree_service=tree_service,
            session_key=session_key,
            run_id=run_id,
            node_id=node.id,
        )


def _tree_tool_function_nodes_include(
    *,
    tree_service: ContextTreeService,
    session_key: str,
    schema_names: frozenset[str],
) -> bool:
    return tool_function_nodes_include(
        tree_service.list_tool_nodes_by_kind(
            session_key,
            kinds=("tool_function",),
        ),
        schema_names=schema_names,
    )


def _expand_context_node_if_present(
    *,
    tree_service: ContextTreeService,
    session_key: str,
    run_id: str,
    node_id: str,
) -> None:
    node = tree_service.get_node(session_key, node_id)
    if node is None or not node.state.collapsed or not node.supports(ContextAction.EXPAND):
        return
    tree_service.apply_action(
        ContextActionInput(
            session_key=session_key,
            run_id=run_id,
            node_id=node_id,
            action=ContextAction.EXPAND,
        ),
    )
