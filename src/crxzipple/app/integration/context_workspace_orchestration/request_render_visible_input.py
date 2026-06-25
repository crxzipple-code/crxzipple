"""Visible input summary helpers for request render snapshots."""

from __future__ import annotations

from crxzipple.modules.llm.domain import ToolSchema


def visible_input_summary(
    *,
    included_refs: tuple[dict[str, object], ...],
    protocol_required_refs: tuple[dict[str, object], ...],
    collapsed_refs: tuple[dict[str, object], ...],
    visible_tool_schemas: tuple[ToolSchema, ...],
    control_slice: object | None,
    context_slice: object | None = None,
    control_selected_node_ids: tuple[str, ...] = (),
) -> dict[str, object]:
    summary: dict[str, object] = {
        "debug_body_included": False,
        "full_tree_rendered": False,
        "owner_children_refreshed": False,
        "input_item_ref_count": len(included_refs),
        "protocol_required_ref_count": len(protocol_required_refs),
        "collapsed_ref_count": len(collapsed_refs),
        "tool_schema_count": len(visible_tool_schemas),
        "tool_schema_names": [schema.name for schema in visible_tool_schemas],
        "input_ref_owner_counts": ref_counts(included_refs, "owner_module"),
        "input_ref_kind_counts": ref_counts(included_refs, "owner_kind"),
    }
    if control_slice is not None:
        summary["control_slice_id"] = getattr(control_slice, "slice_id", None)
        summary["included_node_count"] = len(control_selected_node_ids)
        summary["control_slice_selected_ref_count"] = len(
            getattr(control_slice, "selected_refs", ()) or (),
        )
        summary["control_slice_active_tool_count"] = len(
            getattr(control_slice, "active_tools", ()) or (),
        )
    if context_slice is not None:
        summary["context_slice_id"] = getattr(context_slice, "slice_id", None)
        summary["context_slice_item_count"] = len(
            getattr(context_slice, "items", ()) or (),
        )
        summary["context_slice_active_tool_count"] = len(
            getattr(context_slice, "active_tools", ()) or (),
        )
    return {
        key: value
        for key, value in summary.items()
        if value not in (None, "", {}, [])
    }


def ref_counts(
    refs: tuple[dict[str, object], ...],
    key: str,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ref in refs:
        raw_value = ref.get(key)
        value = raw_value.strip() if isinstance(raw_value, str) else ""
        if not value:
            value = "unknown"
        counts[value] = counts.get(value, 0) + 1
    return counts
