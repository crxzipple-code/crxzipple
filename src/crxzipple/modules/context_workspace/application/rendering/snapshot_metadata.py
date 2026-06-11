from __future__ import annotations

from crxzipple.modules.context_workspace.application import root_nodes
from crxzipple.modules.context_workspace.domain import ContextNode
from crxzipple.shared.context_render_budget import (
    CONTEXT_RENDER_BUDGET_METADATA_FIELDS,
    context_render_budget_metadata,
)


def runtime_contract_metadata(nodes: tuple[ContextNode, ...]) -> dict[str, object]:
    for node in nodes:
        if node.id != "runtime.contract":
            continue
        return {
            "node_id": node.id,
            "contract_version": str(node.metadata.get("contract_version") or ""),
            "content_hash": str(node.metadata.get("content_hash") or ""),
            "revision": node.revision,
        }
    return {}


def root_node_ids(nodes: tuple[ContextNode, ...]) -> tuple[str, ...]:
    root_node_items = tuple(node for node in nodes if node.parent_id is None)
    root_order = {
        node_id: index
        for index, node_id in enumerate(root_nodes.ROOT_SECTION_NODE_IDS)
    }
    return tuple(
        node.id
        for node in sorted(
            root_node_items,
            key=lambda node: (
                root_order.get(node.id, len(root_order)),
                node.display_order,
                node.id,
            ),
        )
    )


def render_snapshot_metadata_defaults(
    metadata: dict[str, object],
    *,
    nodes: tuple[ContextNode, ...],
) -> dict[str, object]:
    payload = dict(metadata)
    payload.setdefault("tree_schema_version", root_nodes.CONTEXT_TREE_SCHEMA_VERSION)
    payload.setdefault("root_node_ids", list(root_node_ids(nodes)))
    payload.setdefault(
        "context_instructions_node_id",
        root_nodes.CONTEXT_INSTRUCTIONS_NODE_ID,
    )
    payload.setdefault(
        "execution_current_node_id",
        root_nodes.EXECUTION_CURRENT_NODE_ID,
    )
    payload.setdefault(
        "session_current_node_id",
        root_nodes.SESSION_CURRENT_NODE_ID,
    )
    return payload


__all__ = [
    "CONTEXT_RENDER_BUDGET_METADATA_FIELDS",
    "context_render_budget_metadata",
    "render_snapshot_metadata_defaults",
    "root_node_ids",
    "runtime_contract_metadata",
]
