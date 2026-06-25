"""Cost and budget helpers for request render snapshot metadata."""

from __future__ import annotations

import json
from typing import Protocol


class RequestRenderCostInput(Protocol):
    context_slice_node_ids: tuple[str, ...]
    control_selected_node_ids: tuple[str, ...]
    included_refs: tuple[dict[str, object], ...]
    visible_tool_schemas: tuple[object, ...]
    projected_input_items: tuple[dict[str, object], ...]


def context_slice_builder_timings(context_slice: object | None) -> dict[str, object]:
    if context_slice is None:
        return {}
    for source in (
        getattr(context_slice, "metadata", None),
        getattr(getattr(context_slice, "report", None), "metadata", None),
    ):
        if not isinstance(source, dict):
            continue
        timings = source.get("context_slice_builder_timings")
        if isinstance(timings, dict):
            return {
                str(key): value
                for key, value in timings.items()
                if isinstance(value, int | float)
            }
    return {}


def request_render_cost(
    data: RequestRenderCostInput,
) -> dict[str, object]:
    context_selected_node_count = len(data.context_slice_node_ids)
    control_selected_node_count = len(data.control_selected_node_ids)
    return {
        "selected_node_count": (
            context_selected_node_count
            if context_selected_node_count
            else control_selected_node_count
        ),
        "control_selected_node_count": control_selected_node_count,
        "context_selected_node_count": context_selected_node_count,
        "selected_session_item_count": len(data.included_refs),
        "provider_visible_tool_count": len(data.visible_tool_schemas),
        "projected_input_item_count": len(data.projected_input_items),
        "rendered_input_char_count": rendered_input_char_count(
            data.projected_input_items,
        ),
        "elapsed_ms": None,
    }


def rendered_input_char_count(
    projected_input_items: tuple[dict[str, object], ...],
) -> int:
    try:
        rendered = json.dumps(
            projected_input_items,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
    except (TypeError, ValueError):
        rendered = str(projected_input_items)
    return len(rendered)


def transcript_budget_summary(budget: dict[str, object]) -> dict[str, object]:
    summary: dict[str, object] = {}
    for key in (
        "source",
        "truncated",
        "protocol_required_preserved",
        "selected_item_count",
        "available_item_count",
        "collapsed_count",
    ):
        value = budget.get(key)
        if value is not None:
            summary[key] = value
    frontier = budget.get("frontier")
    if isinstance(frontier, dict):
        summary["frontier"] = dict(frontier)
    tool_result_stats = budget.get("tool_result_stats")
    if isinstance(tool_result_stats, dict):
        summary["tool_result_stats"] = dict(tool_result_stats)
    return summary
