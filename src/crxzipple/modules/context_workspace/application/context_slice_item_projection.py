from __future__ import annotations

from typing import Protocol

from crxzipple.modules.context_workspace.application.context_control_projection import (
    session_item_id_from_protocol_ref,
)
from crxzipple.modules.context_workspace.application.models import ContextSliceItem
from crxzipple.modules.context_workspace.domain import ContextNode


_HANDLE_ONLY_OWNERS = frozenset(
    {
        "tool",
        "skills",
        "memory",
        "artifacts",
        "workspace",
        "agent",
    },
)
_EMBEDDED_CONTENT_OWNERS = frozenset(
    {
        "context_workspace",
        "llm",
        "orchestration",
        "runtime",
    },
)


class SessionItemResolver(Protocol):
    def get_item(self, item_id: str) -> object:
        ...


def context_slice_item(
    node: ContextNode,
    *,
    session_item_resolver: SessionItemResolver | None = None,
    session_item_max_chars: int | None = None,
) -> tuple[ContextSliceItem, dict[str, object] | None]:
    text = node.content if _node_allows_embedded_content(node) else ""
    content: object | None = None
    owner_ref = dict(node.owner_ref)
    owner_resolution = _default_owner_resolution(node)
    metadata = {
        "summary_mode": node.state.summary_mode,
        "status": node.state.status,
        "render_priority": node.state.render_priority,
        "render_reason": node.state.render_reason,
        "freshness": node.freshness,
        "resolved_from_owner": False,
        "owner_resolution": owner_resolution,
    }
    unresolved_ref: dict[str, object] | None = None
    if node.owner == "session":
        (
            resolved_text,
            resolved_content,
            resolved_owner_ref,
            unresolved_ref,
        ) = _resolve_session_slice_item(
            node,
            session_item_resolver=session_item_resolver,
            max_chars=session_item_max_chars,
        )
        owner_ref.update(resolved_owner_ref)
        if resolved_content is not None:
            content = resolved_content
            metadata["resolved_from_owner"] = True
            metadata["owner_resolution"] = "owner_resolved"
        if resolved_text is not None:
            text = resolved_text
            metadata["resolved_from_owner"] = True
            metadata["owner_resolution"] = "owner_resolved"
        elif unresolved_ref is not None:
            metadata["owner_resolution"] = "owner_unresolved"
    item = ContextSliceItem(
        item_id=node.id,
        node_id=node.id,
        section=_slice_section_for_node(node),
        owner=node.owner,
        kind=node.kind,
        title=node.title,
        summary=node.summary,
        text=text,
        content=content,
        owner_ref=owner_ref,
        estimate=node.estimate,
        metadata=metadata,
    )
    return item, unresolved_ref


def included_session_item_ids(items: list[ContextSliceItem]) -> frozenset[str]:
    ids: set[str] = set()
    for item in items:
        text = _metadata_text(item.owner_ref.get("session_item_id"))
        if text is not None:
            ids.add(text)
    return frozenset(ids)


def protocol_required_slice_items(
    value: object,
    *,
    existing_session_item_ids: frozenset[str],
    session_item_resolver: SessionItemResolver | None,
) -> tuple[list[ContextSliceItem], list[dict[str, object]]]:
    if not isinstance(value, (list, tuple)):
        return [], []
    items: list[ContextSliceItem] = []
    unresolved: list[dict[str, object]] = []
    for ref in value:
        if not isinstance(ref, dict):
            continue
        session_item_id = session_item_id_from_protocol_ref(ref)
        if session_item_id is None or session_item_id in existing_session_item_ids:
            continue
        item, unresolved_ref = _protocol_required_slice_item(
            ref,
            session_item_id=session_item_id,
            session_item_resolver=session_item_resolver,
        )
        if item is not None:
            items.append(item)
        if unresolved_ref is not None:
            unresolved.append(unresolved_ref)
    return items, unresolved


def _protocol_required_slice_item(
    ref: dict[str, object],
    *,
    session_item_id: str,
    session_item_resolver: SessionItemResolver | None,
) -> tuple[ContextSliceItem | None, dict[str, object] | None]:
    if session_item_resolver is None:
        return None, {
            "owner": "session",
            "kind": _metadata_text(ref.get("kind")) or "session_item",
            "owner_ref": dict(ref),
            "reason": "session_item_resolver_unavailable",
        }
    try:
        session_item = session_item_resolver.get_item(session_item_id)
    except Exception as exc:  # owner query errors stay in loss report only
        return None, {
            "owner": "session",
            "kind": _metadata_text(ref.get("kind")) or "session_item",
            "owner_ref": dict(ref),
            "reason": "session_item_resolve_failed",
            "error_type": type(exc).__name__,
        }
    owner_ref = {**dict(ref), **_session_item_owner_ref(session_item)}
    owner_ref["session_item_id"] = session_item_id
    raw_kind = _metadata_text(ref.get("kind"))
    if raw_kind == "tool_call":
        kind = "runtime_assistant_tool_call"
    elif raw_kind == "tool_result":
        kind = "runtime_tool_result"
    else:
        kind = "session_item"
    text = _session_item_model_text(session_item) or ""
    content = _session_item_model_content(session_item)
    sequence_no = owner_ref.get("sequence_no")
    title = (
        f"{sequence_no}. {owner_ref.get('role')}"
        if sequence_no not in (None, "")
        else _metadata_text(ref.get("title")) or kind
    )
    return (
        ContextSliceItem(
            item_id=_metadata_text(ref.get("node_id"))
            or f"protocol.session_item.{session_item_id}",
            node_id=_metadata_text(ref.get("node_id")),
            section="tool_results" if kind == "runtime_tool_result" else "history",
            owner="session",
            kind=kind,
            title=str(title),
            summary=_metadata_text(ref.get("summary")) or "",
            text=text,
            content=content,
            owner_ref=owner_ref,
            metadata={
                "summary_mode": "full",
                "status": "available",
                "render_priority": 0,
                "render_reason": "protocol_required",
                "freshness": "live",
                "resolved_from_owner": True,
                "owner_resolution": "owner_resolved",
                "protocol_required": True,
            },
        ),
        None,
    )


def _node_allows_embedded_content(node: ContextNode) -> bool:
    if node.owner == "session":
        return False
    if node.owner in _HANDLE_ONLY_OWNERS:
        return False
    return node.owner in _EMBEDDED_CONTENT_OWNERS


def _default_owner_resolution(node: ContextNode) -> str:
    if _node_allows_embedded_content(node):
        return "embedded"
    if node.owner == "session":
        return "owner_resolved"
    return "handle_only"


def _resolve_session_slice_item(
    node: ContextNode,
    *,
    session_item_resolver: SessionItemResolver | None,
    max_chars: int | None = None,
) -> tuple[str | None, object | None, dict[str, object], dict[str, object] | None]:
    session_item_id = _metadata_text(node.owner_ref.get("session_item_id"))
    if session_item_id is None:
        return None, None, {}, None
    if session_item_resolver is None:
        return None, None, {}, {
            "node_id": node.id,
            "owner": node.owner,
            "kind": node.kind,
            "owner_ref": dict(node.owner_ref),
            "reason": "session_item_resolver_unavailable",
        }
    try:
        item = session_item_resolver.get_item(session_item_id)
    except Exception as exc:  # owner query errors stay in loss report only
        return None, None, {}, {
            "node_id": node.id,
            "owner": node.owner,
            "kind": node.kind,
            "owner_ref": dict(node.owner_ref),
            "reason": "session_item_resolve_failed",
            "error_type": type(exc).__name__,
        }
    text = _session_item_model_text(item)
    content = _session_item_model_content(item)
    text, content = _truncate_session_projection(
        text,
        content,
        max_chars=max_chars,
    )
    owner_ref = _session_item_owner_ref(item)
    if (
        text is None
        and content is None
        and not _session_item_has_structured_model_projection(owner_ref)
    ):
        return None, None, owner_ref, {
            "node_id": node.id,
            "owner": node.owner,
            "kind": node.kind,
            "owner_ref": dict(node.owner_ref),
            "reason": "session_item_has_no_model_content",
        }
    return text, content, owner_ref, None


def _session_item_has_structured_model_projection(
    owner_ref: dict[str, object],
) -> bool:
    if owner_ref.get("model_visible") is False:
        return False
    kind = _metadata_text(owner_ref.get("kind"))
    tool_call_id = _metadata_text(
        owner_ref.get("tool_call_id"),
    ) or _metadata_text(owner_ref.get("call_id"))
    tool_name = _metadata_text(owner_ref.get("tool_name")) or _metadata_text(
        owner_ref.get("name"),
    )
    if kind == "tool_call":
        return tool_call_id is not None and tool_name is not None
    if kind == "tool_result":
        return tool_call_id is not None
    return False


def _truncate_session_projection(
    text: str | None,
    content: object | None,
    *,
    max_chars: int | None,
) -> tuple[str | None, object | None]:
    if max_chars is None or max_chars <= 0:
        return text, content
    if text is None or len(text) <= max_chars:
        return text, content
    truncated = text[-max_chars:]
    return truncated, [{"type": "text", "text": truncated}]


def _slice_section_for_node(node: ContextNode) -> str:
    if node.id in {"run.goal", "work.plan"} or node.id.startswith("task."):
        return "task"
    if node.owner == "runtime" or node.id.startswith("run."):
        return "runtime"
    if node.owner == "session":
        if node.kind in {"tool_interaction", "runtime_tool_result"}:
            return "tool_results"
        return "history"
    if node.owner == "skills":
        return "skills"
    if node.owner == "memory":
        return "memory"
    if node.owner == "artifacts":
        return "artifacts"
    if node.owner == "workspace":
        return "workspace"
    return "runtime"


def _session_item_model_text(item: object) -> str | None:
    payload = getattr(item, "content_payload", None)
    if not isinstance(payload, dict):
        return None
    blocks = payload.get("blocks")
    if isinstance(blocks, list):
        lines = tuple(
            text
            for block in blocks
            for text in (_content_block_model_text(block),)
            if text is not None
        )
        if lines:
            return "\n".join(lines)
    content = payload.get("content")
    if isinstance(content, list):
        lines = tuple(
            text
            for block in content
            for text in (_content_block_model_text(block),)
            if text is not None
        )
        if lines:
            return "\n".join(lines)
    for key in ("text", "content", "summary"):
        value = _metadata_text(payload.get(key))
        if value is not None:
            return value
    return None


def _session_item_model_content(item: object) -> object | None:
    payload = getattr(item, "content_payload", None)
    if not isinstance(payload, dict):
        return None
    blocks = payload.get("blocks")
    if isinstance(blocks, list) and blocks:
        return [dict(block) if isinstance(block, dict) else block for block in blocks]
    content = payload.get("content")
    if isinstance(content, list) and content:
        return [dict(block) if isinstance(block, dict) else block for block in content]
    return None


def _session_item_owner_ref(item: object) -> dict[str, object]:
    payload = getattr(item, "content_payload", None)
    metadata = getattr(item, "metadata", None)
    role = _metadata_text(getattr(item, "role", None))
    owner_ref: dict[str, object] = {}
    item_id = _metadata_text(getattr(item, "id", None))
    session_id = _metadata_text(getattr(item, "session_id", None))
    sequence_no = getattr(item, "sequence_no", None)
    kind = _metadata_text(getattr(item, "kind", None))
    source_kind = _metadata_text(getattr(item, "source_kind", None))
    source_module = _metadata_text(getattr(item, "source_module", None))
    source_id = _metadata_text(getattr(item, "source_id", None))
    provider_item_type = _metadata_text(getattr(item, "provider_item_type", None))
    model_visible = getattr(item, "model_visible", None)
    if item_id is not None:
        owner_ref["session_item_id"] = item_id
    if session_id is not None:
        owner_ref["session_id"] = session_id
    if isinstance(sequence_no, int):
        owner_ref["sequence_no"] = sequence_no
    if kind is not None:
        owner_ref["kind"] = kind
    if role is not None:
        owner_ref["role"] = role
    if isinstance(model_visible, bool):
        owner_ref["model_visible"] = model_visible
    if source_kind is not None:
        owner_ref["source_kind"] = source_kind
    if source_module is not None:
        owner_ref["source_module"] = source_module
    if source_id is not None:
        owner_ref["source_id"] = source_id
    if provider_item_type is not None:
        owner_ref["provider_item_type"] = provider_item_type
    if not isinstance(payload, dict):
        payload = {}
    if not isinstance(metadata, dict):
        metadata = {}
    runtime_semantic_kind = _metadata_text(metadata.get("runtime_semantic_kind"))
    if runtime_semantic_kind is not None:
        owner_ref["runtime_semantic_kind"] = runtime_semantic_kind
    for key in ("tool_call_id", "tool_name", "tool_run_id", "llm_response_item_id"):
        value = _metadata_text(metadata.get(key)) or _metadata_text(payload.get(key))
        if value is not None:
            owner_ref[key] = value
    if isinstance(payload.get("arguments"), (dict, list, str, int, float, bool)):
        owner_ref["arguments"] = payload.get("arguments")
    call_id = _metadata_text(payload.get("call_id"))
    if call_id is not None and "tool_call_id" not in owner_ref:
        owner_ref["tool_call_id"] = call_id
    name = _metadata_text(payload.get("name"))
    if name is not None and "tool_name" not in owner_ref:
        owner_ref["tool_name"] = name
    return owner_ref


def _content_block_model_text(block: object) -> str | None:
    if not isinstance(block, dict):
        return None
    block_type = _metadata_text(block.get("type")) or "text"
    if block_type == "text":
        return _metadata_text(block.get("text"))
    if block_type in {"image", "image_ref"}:
        name = _metadata_text(block.get("name")) or _metadata_text(block.get("filename"))
        artifact_id = _metadata_text(block.get("artifact_id"))
        label = name or artifact_id or "image"
        return f"[image:{label}]"
    if block_type in {"file", "file_ref"}:
        name = _metadata_text(block.get("name")) or _metadata_text(block.get("filename"))
        artifact_id = _metadata_text(block.get("artifact_id"))
        label = name or artifact_id or "file"
        return f"[file:{label}]"
    return _metadata_text(block.get("text")) or f"[{block_type}]"


def _metadata_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


__all__ = [
    "SessionItemResolver",
    "context_slice_item",
    "included_session_item_ids",
    "protocol_required_slice_items",
]
