from __future__ import annotations

from crxzipple.modules.context_workspace.application.models import ContextControlRef
from crxzipple.modules.context_workspace.domain import ContextNode


def merge_control_refs_with_protocol_required(
    *,
    selected_nodes: tuple[ContextNode, ...],
    protocol_required_refs: tuple[dict[str, object], ...],
) -> tuple[ContextControlRef, ...]:
    selected_refs = [context_control_ref(node) for node in selected_nodes]
    selected_session_item_ids = {
        text
        for item in selected_refs
        for text in (
            _metadata_text(item.owner_ref.get("session_item_id")),
            _metadata_text(item.owner_ref.get("item_id")),
            _metadata_text(item.owner_ref.get("owner_id")),
        )
        if text is not None
    }
    selected_node_ids = {item.node_id for item in selected_refs}
    for ref in protocol_required_refs:
        control_ref = _control_ref_from_session_ref(ref)
        if control_ref is None:
            continue
        ref_session_item_id = (
            _metadata_text(control_ref.owner_ref.get("session_item_id"))
            or _metadata_text(control_ref.owner_ref.get("item_id"))
            or _metadata_text(control_ref.owner_ref.get("owner_id"))
        )
        if control_ref.node_id in selected_node_ids:
            continue
        if (
            ref_session_item_id is not None
            and ref_session_item_id in selected_session_item_ids
        ):
            continue
        selected_refs.append(control_ref)
        selected_node_ids.add(control_ref.node_id)
        if ref_session_item_id is not None:
            selected_session_item_ids.add(ref_session_item_id)
    return tuple(selected_refs)


def context_control_ref(node: ContextNode) -> ContextControlRef:
    return ContextControlRef(
        node_id=node.id,
        owner=node.owner,
        kind=node.kind,
        title=node.title,
        owner_ref=dict(node.owner_ref),
        metadata={
            "status": node.state.status,
            "collapsed": node.state.collapsed,
            "pinned": node.state.pinned,
            "schema_enabled": node.state.schema_enabled,
            "included_in_next_tool_surface": (
                node.state.included_in_next_tool_surface
            ),
            "render_priority": node.state.render_priority,
            "revision": node.revision,
        },
    )


def session_item_id_from_protocol_ref(ref: dict[str, object]) -> str | None:
    explicit = (
        _metadata_text(ref.get("session_item_id"))
        or _metadata_text(ref.get("item_id"))
        or _metadata_text(ref.get("call_session_item_id"))
        or _metadata_text(ref.get("result_session_item_id"))
    )
    if explicit is not None:
        return explicit
    if _metadata_text(ref.get("source_owner_kind")) == "session_item":
        source_owner_id = _metadata_text(ref.get("source_owner_id"))
        if source_owner_id is not None:
            return source_owner_id
    if _metadata_text(ref.get("owner_kind")) == "session_item":
        return _metadata_text(ref.get("owner_id"))
    return None


def _control_ref_from_session_ref(
    ref: dict[str, object],
) -> ContextControlRef | None:
    item_id = session_item_id_from_protocol_ref(ref)
    if item_id is None:
        return None
    owner_ref = dict(ref)
    owner_ref.setdefault("session_item_id", item_id)
    owner_ref.setdefault("item_id", item_id)
    owner_ref.setdefault("owner_id", item_id)
    node_id = _metadata_text(ref.get("node_id")) or f"session.item.{item_id}"
    kind = _metadata_text(ref.get("owner_kind")) or _metadata_text(ref.get("kind"))
    if kind is None or kind in {"message", "tool_result"}:
        kind = "session_item"
    role = _metadata_text(ref.get("role"))
    title = f"{role} {item_id}" if role else item_id
    return ContextControlRef(
        node_id=node_id,
        owner="session",
        kind=kind,
        title=title,
        owner_ref=owner_ref,
        metadata={
            "status": _metadata_text(ref.get("status")) or "known",
            "protocol_required": True,
            "tree_backed": False,
        },
    )


def _metadata_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


__all__ = [
    "context_control_ref",
    "merge_control_refs_with_protocol_required",
    "session_item_id_from_protocol_ref",
]
