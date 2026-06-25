from __future__ import annotations

from crxzipple.modules.context_workspace.domain import ContextNode


def collapsed_ref(node: ContextNode) -> dict[str, object]:
    return {
        "node_id": node.id,
        "owner": node.owner,
        "kind": node.kind,
        "title": node.title,
    }


def archived_ref(node: ContextNode) -> dict[str, object]:
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
    return ref


def metadata_dict_list(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(dict(item) for item in value if isinstance(item, dict))


def metadata_string_set(value: object) -> frozenset[str]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        return frozenset()
    return frozenset(
        text
        for item in value
        if isinstance(item, str) and (text := item.strip())
    )


def _metadata_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


__all__ = [
    "archived_ref",
    "collapsed_ref",
    "metadata_dict_list",
    "metadata_string_set",
]
