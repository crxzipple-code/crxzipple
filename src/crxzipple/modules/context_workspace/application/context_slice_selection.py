from __future__ import annotations

from crxzipple.modules.context_workspace.domain import (
    ContextNode,
    ContextWorkspaceValidationError,
)
from crxzipple.modules.context_workspace.application.rendering.xml_renderer import (
    tree_snapshot_visible_nodes,
)


def normalize_slice_audience(value: str) -> str:
    normalized = str(value or "").strip() or "llm_request"
    allowed = {
        "llm_request",
        "user_timeline",
        "trace_timeline",
        "debug_tree",
        "operations_projection",
    }
    if normalized not in allowed:
        raise ContextWorkspaceValidationError(
            f"Unsupported context observation slice audience: {normalized}",
        )
    return normalized


def included_nodes_for_slice(
    *,
    nodes: tuple[ContextNode, ...],
    visible_nodes: tuple[ContextNode, ...],
    audience: str,
    request_metadata: dict[str, object],
) -> tuple[ContextNode, ...]:
    if audience == "llm_request":
        input_item_ids = _slice_ref_ids(request_metadata.get("input_item_refs"))
        included = [
            node
            for node in visible_nodes
            if _node_included_in_slice(node, audience=audience)
            and not _unmatched_session_input_anchor(
                node,
                input_item_ids=input_item_ids,
            )
        ]
        if input_item_ids:
            included_ids = {node.id for node in included}
            for node in visible_nodes:
                if node.id in included_ids:
                    continue
                if not _node_matches_slice_ref(node, input_item_ids):
                    continue
                included.append(node)
                included_ids.add(node.id)
    else:
        included = [
            node
            for node in visible_nodes
            if _node_included_in_slice(node, audience=audience)
        ]
    if audience != "llm_request":
        return tuple(included)
    protocol_required_ids = _slice_ref_ids(
        request_metadata.get("protocol_required_refs"),
    )
    included_ids = {node.id for node in included}
    for node in nodes:
        if node.id in included_ids or node.state.archived:
            continue
        if node.owner == "session" and (
            _node_protocol_required(node)
            or _node_matches_protocol_required_ref(node, protocol_required_ids)
        ):
            included.append(node)
            included_ids.add(node.id)
    return tuple(included)


def visible_nodes_for_slice(
    nodes: tuple[ContextNode, ...],
    *,
    audience: str,
) -> tuple[ContextNode, ...]:
    if audience == "debug_tree":
        return nodes
    return tuple(
        node
        for node in tree_snapshot_visible_nodes(nodes)
        if not node.state.archived
    )


def _slice_ref_ids(value: object) -> frozenset[str]:
    if not isinstance(value, (list, tuple)):
        return frozenset()
    ids: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        for key in ("node_id", "owner_id", "item_id", "session_item_id"):
            text = _metadata_text(item.get(key))
            if text is not None:
                ids.add(text)
    return frozenset(ids)


def _node_matches_protocol_required_ref(
    node: ContextNode,
    protocol_required_ids: frozenset[str],
) -> bool:
    return _node_matches_slice_ref(node, protocol_required_ids)


def _node_matches_slice_ref(
    node: ContextNode,
    ref_ids: frozenset[str],
) -> bool:
    if not ref_ids:
        return False
    if node.id in ref_ids:
        return True
    for key in ("owner_id", "item_id", "session_item_id"):
        text = _metadata_text(node.owner_ref.get(key))
        if text is not None and text in ref_ids:
            return True
    return False


def _unmatched_session_input_anchor(
    node: ContextNode,
    *,
    input_item_ids: frozenset[str],
) -> bool:
    if not input_item_ids:
        return False
    if node.owner != "session" or node.kind != "session_item":
        return False
    if node.state.pinned or node.state.opened:
        return False
    if not node.state.included_in_next_slice:
        return False
    return not _node_matches_slice_ref(node, input_item_ids)


def _node_included_in_slice(node: ContextNode, *, audience: str) -> bool:
    if audience == "debug_tree":
        return True
    if audience == "user_timeline":
        return _node_included_in_user_timeline_slice(node)
    if audience == "trace_timeline":
        return _node_included_in_trace_timeline_slice(node)
    if audience == "operations_projection":
        return _node_included_in_operations_projection_slice(node)
    if audience == "llm_request":
        return _node_included_in_llm_request_slice(node)
    return False


def _node_included_in_llm_request_slice(node: ContextNode) -> bool:
    if node.state.included_in_next_slice:
        return True
    if node.state.pinned or node.state.opened:
        return True
    if node.owner == "session" and node.kind in {
        "runtime_tool_result",
        "runtime_assistant_tool_call",
    }:
        return _node_protocol_required(node)
    if node.owner == "session" and node.kind == "tool_interaction":
        return not _metadata_bool(node.owner_ref.get("has_artifact_content_candidates"))
    if node.owner == "session" and node.kind in {
        "runtime_assistant_message",
        "runtime_assistant_progress",
        "runtime_session_message",
        "session_segment",
        "session_item",
        "session_item_range",
    }:
        if node.kind == "session_segment":
            return (
                _metadata_text(node.owner_ref.get("segment_kind")) == "compacted"
                and _metadata_bool(node.owner_ref.get("has_summary"))
            )
        return True
    if node.owner == "orchestration" and node.kind == "run_goal":
        return True
    if node.owner in {"skills", "memory", "artifacts", "workspace"}:
        return (
            node.state.pinned
            or node.state.opened
            or node.state.included_in_next_slice
        )
    return False


def _node_included_in_user_timeline_slice(node: ContextNode) -> bool:
    if node.state.included_in_next_slice or node.state.pinned or node.state.opened:
        return True
    if node.owner != "session":
        return False
    return node.kind in {
        "session_turn",
        "session_step",
        "runtime_assistant_progress",
        "runtime_assistant_message",
        "runtime_session_message",
        "runtime_tool_run",
        "runtime_tool_result",
        "session_item",
        "session_item_range",
        "tool_interaction",
    }


def _node_included_in_trace_timeline_slice(node: ContextNode) -> bool:
    if node.state.included_in_next_slice or node.state.pinned or node.state.opened:
        return True
    if node.owner in {"session", "orchestration", "runtime", "agent"}:
        return True
    if node.owner == "tool":
        return node.kind in {"tool_function", "tool_group", "tool_source"}
    return False


def _node_included_in_operations_projection_slice(node: ContextNode) -> bool:
    if node.state.included_in_next_slice or node.state.pinned or node.state.opened:
        return True
    if node.owner in {"session", "orchestration", "runtime", "agent", "tool"}:
        return True
    return node.owner in {"skills", "memory", "artifacts", "workspace"} and (
        node.state.pinned or node.state.opened
    )


def _node_protocol_required(node: ContextNode) -> bool:
    if _metadata_bool(node.owner_ref.get("protocol_required")):
        return True
    if _metadata_bool(node.metadata.get("protocol_required")):
        return True
    return (
        _metadata_text(node.owner_ref.get("budget_class")) == "protocol_required"
        or _metadata_text(node.metadata.get("budget_class")) == "protocol_required"
    )


def _metadata_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _metadata_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


__all__ = [
    "included_nodes_for_slice",
    "normalize_slice_audience",
    "visible_nodes_for_slice",
]
