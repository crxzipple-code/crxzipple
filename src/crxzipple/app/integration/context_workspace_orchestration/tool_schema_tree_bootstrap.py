"""Context-tree fallback for default tool schema bootstrap."""

from __future__ import annotations

from crxzipple.modules.context_workspace.application import ContextTreeService
from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
    RuntimeLlmRequestDraft,
)

from ._metadata import metadata_positive_int, metadata_string_list, metadata_text
from .tool_schema_group_refs import metadata_tool_schema_group_refs
from .tool_schema_tree_nodes import (
    default_tool_schema_group_refs_from_source_policy,
    expand_context_node_if_present,
    expand_tool_bundles_for_default_schema_ids,
)


def resolve_default_tool_schema_metadata_from_tree(
    *,
    tree_service: ContextTreeService,
    session_key: str,
    run_id: str,
    draft: RuntimeLlmRequestDraft,
) -> dict[str, object]:
    direct_schema_ids = metadata_string_list(
        draft.flow_hint.get("default_tool_schema_ids"),
    )
    if direct_schema_ids:
        expand_tool_bundles_for_default_schema_ids(
            tree_service=tree_service,
            session_key=session_key,
            run_id=run_id,
            schema_ids=tuple(direct_schema_ids),
        )
    group_refs = metadata_tool_schema_group_refs(
        draft.flow_hint.get("default_tool_schema_group_refs"),
    )
    group_ref_source = "runtime_request_flow_hint.group_bootstrap"
    if not group_refs:
        group_refs = default_tool_schema_group_refs_from_source_policy(
            tree_service=tree_service,
            session_key=session_key,
            run_id=run_id,
        )
        group_ref_source = "source_runtime_request.default_tool_schema_group_refs"
    if not group_refs:
        return {}
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
    for ref in group_refs:
        source_id = ref.get("source_id")
        if source_id is None:
            continue
        bundle_node = next(
            (
                node
                for node in bundle_nodes
                if node.owner == "tool"
                and node.kind == "tool_bundle"
                and node.owner_ref.get("source_id") == source_id
            ),
            None,
        )
        if bundle_node is not None:
            expand_context_node_if_present(
                tree_service=tree_service,
                session_key=session_key,
                run_id=run_id,
                node_id=bundle_node.id,
            )

    group_nodes = tree_service.list_tool_nodes_by_kind(
        session_key,
        kinds=("tool_bundle_group",),
    )
    default_schema_ids: list[str] = []
    default_sources: list[str] = []
    default_priorities: dict[str, int] = {}
    default_reasons: dict[str, str] = {}
    matched_groups: list[dict[str, str]] = []
    for group_index, ref in enumerate(group_refs):
        group_node = _find_tool_group_node(group_nodes, ref)
        if group_node is None:
            continue
        expand_context_node_if_present(
            tree_service=tree_service,
            session_key=session_key,
            run_id=run_id,
            node_id=group_node.id,
        )
        group_schema_ids = metadata_string_list(
            group_node.metadata.get("default_tool_schema_ids"),
        )
        max_count = metadata_positive_int(
            group_node.metadata.get("default_tool_schema_max_count"),
        )
        if max_count is not None:
            group_schema_ids = group_schema_ids[:max_count]
        group_priority = _group_priority(
            ref,
            group_node=group_node,
            fallback=group_index,
        )
        reason = metadata_text(ref.get("reason"))
        for schema_index, schema_id in enumerate(group_schema_ids):
            if schema_id not in default_schema_ids:
                default_schema_ids.append(schema_id)
            default_priorities.setdefault(
                schema_id,
                group_priority + schema_index,
            )
            if reason is not None:
                default_reasons.setdefault(schema_id, reason)
        source = metadata_text(group_node.metadata.get("default_tool_schema_source"))
        if source is not None and source not in default_sources:
            default_sources.append(source)
        matched_groups.append(
            {
                "node_id": group_node.id,
                "source_id": str(group_node.owner_ref.get("source_id") or ""),
                "group_key": str(group_node.owner_ref.get("group_key") or ""),
                "priority": str(group_priority),
                **({"reason": reason} if reason is not None else {}),
            },
        )
    if not default_schema_ids:
        return {}
    return {
        "default_tool_schema_ids": default_schema_ids,
        "default_tool_schema_source": (
            ",".join(default_sources)
            if default_sources
            else group_ref_source
        ),
        "default_tool_schema_group_refs": [dict(ref) for ref in group_refs],
        "default_tool_schema_group_matches": matched_groups,
        "default_tool_schema_priorities": dict(default_priorities),
        "default_tool_schema_reasons": dict(default_reasons),
    }

def _group_priority(
    ref: dict[str, str],
    *,
    group_node: object,
    fallback: int,
) -> int:
    source_priority = metadata_positive_int(ref.get("priority")) or 100
    raw_group_order = getattr(group_node, "metadata", {}).get("order")
    group_order = metadata_positive_int(raw_group_order) or fallback
    return (source_priority * 10_000) + (group_order * 100)


def _find_tool_group_node(nodes: tuple[object, ...], ref: dict[str, str]):
    node_id = ref.get("node_id")
    if node_id is not None:
        return next(
            (
                node
                for node in nodes
                if getattr(node, "id", None) == node_id
                and getattr(node, "owner", None) == "tool"
                and getattr(node, "kind", None) == "tool_bundle_group"
            ),
            None,
        )
    source_id = ref.get("source_id")
    group_key = ref.get("group_key")
    if source_id is None or group_key is None:
        return None
    return next(
        (
            node
            for node in nodes
            if getattr(node, "owner", None) == "tool"
            and getattr(node, "kind", None) == "tool_bundle_group"
            and node.owner_ref.get("source_id") == source_id
            and node.owner_ref.get("group_key") == group_key
        ),
        None,
    )
