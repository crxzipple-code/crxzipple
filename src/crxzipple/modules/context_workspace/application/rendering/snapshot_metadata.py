from __future__ import annotations

from crxzipple.modules.context_workspace.application import root_nodes
from crxzipple.modules.context_workspace.domain import ContextNode
from crxzipple.shared.request_render_budget import (
    REQUEST_RENDER_BUDGET_METADATA_FIELDS,
    request_render_budget_metadata,
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


def snapshot_metadata_defaults(
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
    archived_refs = _archived_refs(nodes)
    payload.setdefault("archived_ref_count", len(archived_refs))
    if archived_refs:
        payload.setdefault("archived_refs", archived_refs)
    return payload


def _archived_refs(nodes: tuple[ContextNode, ...]) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    for node in nodes:
        if not node.state.archived:
            continue
        ref: dict[str, object] = {
            "node_id": node.id,
            "owner": node.owner,
            "kind": node.kind,
            "title": node.title,
            "reason": _metadata_text(node.metadata.get("archived_reason"))
            or _metadata_text(node.owner_ref.get("archived_reason"))
            or "archived",
        }
        for key in (
            "session_key",
            "session_id",
            "session_item_id",
            "sequence_no",
            "summary_item_id",
            "archived_by_compaction_run_id",
            "compacted_segment_id",
            "archived_through_item_sequence_no",
        ):
            value = node.owner_ref.get(key)
            if value not in (None, "", {}, []):
                ref[key] = value
        refs.append(ref)
    return refs


def _metadata_text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


__all__ = [
    "REQUEST_RENDER_BUDGET_METADATA_FIELDS",
    "request_render_budget_metadata",
    "snapshot_metadata_defaults",
    "root_node_ids",
    "runtime_contract_metadata",
]
