"""Context-tree node operations for tool schema bootstrap."""

from __future__ import annotations

from crxzipple.modules.context_workspace.application import (
    ContextActionInput,
    ContextTreeService,
)
from crxzipple.modules.context_workspace.domain import ContextAction

from ._metadata import metadata_positive_int, metadata_string_list, metadata_text
from .tool_schema_group_refs import (
    CORE_DEFAULT_TOOL_GROUPS,
    default_schema_source_ids,
    metadata_tool_schema_group_refs,
    with_default_source_id,
)


def default_tool_schema_group_refs_from_source_policy(
    *,
    tree_service: ContextTreeService,
    session_key: str,
    run_id: str,
) -> list[dict[str, str]]:
    expand_context_node_if_present(
        tree_service=tree_service,
        session_key=session_key,
        run_id=run_id,
        node_id="tools.available",
    )
    bundle_nodes = tree_service.list_tool_nodes_by_kind(
        session_key,
        kinds=("tool_bundle",),
    )
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for bundle_node in bundle_nodes:
        if (
            getattr(bundle_node, "owner", None) != "tool"
            or getattr(bundle_node, "kind", None) != "tool_bundle"
        ):
            continue
        source_id = metadata_text(bundle_node.owner_ref.get("source_id"))
        if source_id is None:
            source_id = metadata_text(bundle_node.metadata.get("source_id"))
        if source_id is None:
            continue
        runtime_request_config = bundle_node.metadata.get("runtime_request")
        if not isinstance(runtime_request_config, dict):
            continue
        source_policy = (
            runtime_request_config.get("default_tool_schema_policy")
            if isinstance(
                runtime_request_config.get("default_tool_schema_policy"),
                dict,
            )
            else {}
        )
        source_priority = metadata_positive_int(source_policy.get("priority"))
        for ref in metadata_tool_schema_group_refs(
            runtime_request_config.get("default_tool_schema_group_refs"),
        ):
            normalized = with_default_source_id(ref, source_id=source_id)
            if normalized is None:
                continue
            group_key = metadata_text(normalized.get("group_key"))
            if (source_id, group_key or "") not in CORE_DEFAULT_TOOL_GROUPS:
                continue
            if source_priority is not None and "priority" not in normalized:
                normalized["priority"] = str(source_priority)
            key = (
                normalized.get("node_id", ""),
                normalized.get("source_id", ""),
                normalized.get("group_key", ""),
            )
            if key in seen:
                continue
            seen.add(key)
            refs.append(normalized)
    return refs


def expand_tool_bundles_for_default_schema_ids(
    *,
    tree_service: ContextTreeService,
    session_key: str,
    run_id: str,
    schema_ids: tuple[str, ...],
) -> None:
    source_ids = default_schema_source_ids(schema_ids)
    expand_context_node_if_present(
        tree_service=tree_service,
        session_key=session_key,
        run_id=run_id,
        node_id="tools.available",
    )
    bundle_nodes = tree_service.list_tool_nodes_by_kind(
        session_key,
        kinds=("tool_bundle",),
    )
    expanded_bundle_ids: set[str] = set()
    for node in bundle_nodes:
        if (
            getattr(node, "owner", None) != "tool"
            or getattr(node, "kind", None) != "tool_bundle"
        ):
            continue
        source_id = metadata_text(node.owner_ref.get("source_id"))
        if source_id is None:
            source_id = metadata_text(node.metadata.get("source_id"))
        if not source_ids or source_id in source_ids:
            expand_context_node_if_present(
                tree_service=tree_service,
                session_key=session_key,
                run_id=run_id,
                node_id=node.id,
            )
            expanded_bundle_ids.add(str(node.id))
    if not expanded_bundle_ids:
        for node in bundle_nodes:
            if (
                getattr(node, "owner", None) != "tool"
                or getattr(node, "kind", None) != "tool_bundle"
            ):
                continue
            expand_context_node_if_present(
                tree_service=tree_service,
                session_key=session_key,
                run_id=run_id,
                node_id=node.id,
            )
    group_nodes = tree_service.list_tool_nodes_by_kind(
        session_key,
        kinds=("tool_bundle_group",),
    )
    wanted_schema_ids = set(schema_ids)
    for node in group_nodes:
        if (
            getattr(node, "owner", None) != "tool"
            or getattr(node, "kind", None) != "tool_bundle_group"
        ):
            continue
        function_ids = set(
            metadata_string_list(node.owner_ref.get("function_ids"))
            + metadata_string_list(node.metadata.get("function_ids"))
            + metadata_string_list(node.metadata.get("default_tool_schema_ids"))
        )
        if wanted_schema_ids.isdisjoint(function_ids):
            continue
        expand_context_node_if_present(
            tree_service=tree_service,
            session_key=session_key,
            run_id=run_id,
            node_id=node.id,
        )


def expand_context_node_if_present(
    *,
    tree_service: ContextTreeService,
    session_key: str,
    run_id: str,
    node_id: str,
) -> None:
    node = tree_service.get_node(session_key, node_id)
    if node is None or not node.state.collapsed:
        return
    tree_service.apply_action(
        ContextActionInput(
            session_key=session_key,
            run_id=run_id,
            node_id=node_id,
            action=ContextAction.EXPAND,
        ),
    )
