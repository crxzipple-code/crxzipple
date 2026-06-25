from __future__ import annotations

from crxzipple.modules.llm.application.session_runtime_item_metrics import (
    session_item_content_chars,
    truncate_item_to_recent_chars,
)
from crxzipple.modules.llm.application.session_runtime_protocol import (
    is_protocol_required_item,
    session_item_budget_ref,
    tool_protocol_diagnostics,
    tool_protocol_normalization_diagnostics,
)
from crxzipple.modules.session.domain import SessionItem


def truncate_items_to_recent_budget(
    items: tuple[SessionItem, ...],
    *,
    max_chars: int | None,
) -> tuple[SessionItem, ...]:
    if max_chars is None or max_chars <= 0:
        return items
    kept: list[tuple[int, SessionItem]] = []
    remaining_chars = max_chars
    for index, item in reversed(tuple(enumerate(items))):
        item_chars = session_item_content_chars(item)
        if (
            not is_protocol_required_item(item)
            and not kept
            and item_chars > remaining_chars
        ):
            item = truncate_item_to_recent_chars(item, remaining_chars)
            item_chars = session_item_content_chars(item)
        if (
            not is_protocol_required_item(item)
            and kept
            and item_chars > remaining_chars
        ):
            continue
        kept.append((index, item))
        remaining_chars = max(0, remaining_chars - item_chars)
    kept.sort(key=lambda entry: entry[0])
    return tuple(item for _, item in kept)


def session_item_budget_report(
    all_items: tuple[SessionItem, ...],
    kept_items: tuple[SessionItem, ...],
    *,
    max_chars: int | None,
    source_items: tuple[SessionItem, ...] | None = None,
) -> dict[str, object]:
    source_items = all_items if source_items is None else source_items
    kept_ids = {item.id for item in kept_items}
    dropped_items = tuple(item for item in all_items if item.id not in kept_ids)
    original_items_by_id = {item.id: item for item in all_items}
    shortened_items = tuple(
        item
        for item in kept_items
        if item.id in original_items_by_id
        and session_item_content_chars(item)
        < session_item_content_chars(original_items_by_id[item.id])
    )
    collapsed_chars = sum(session_item_content_chars(item) for item in dropped_items)
    shortened_chars = sum(
        session_item_content_chars(original_items_by_id[item.id])
        - session_item_content_chars(item)
        for item in shortened_items
        if item.id in original_items_by_id
    )
    protocol_items = tuple(item for item in all_items if is_protocol_required_item(item))
    kept_protocol_ids = {item.id for item in kept_items if is_protocol_required_item(item)}
    source_protocol_diagnostics = tool_protocol_diagnostics(source_items)
    protocol_diagnostics = tool_protocol_diagnostics(kept_items)
    normalization_diagnostics = tool_protocol_normalization_diagnostics(
        source_protocol_diagnostics,
        protocol_diagnostics,
    )
    report: dict[str, object] = {
        "source": "session_items",
        "budget_unit": "chars",
        "max_chars": max_chars,
        "input_item_count": len(all_items),
        "included_item_count": len(kept_items),
        "collapsed_item_count": len(dropped_items),
        "shortened_item_count": len(shortened_items),
        "collapsed_chars": collapsed_chars,
        "shortened_chars": shortened_chars,
        "omitted_chars": collapsed_chars + shortened_chars,
        "truncated": bool(dropped_items or shortened_items),
        "frontier": session_item_frontier(kept_items),
        "included_refs": [session_item_budget_ref(item) for item in kept_items],
        "collapsed_refs": [session_item_budget_ref(item) for item in dropped_items],
        "shortened_refs": [session_item_budget_ref(item) for item in shortened_items],
        "protocol_required_refs": [
            session_item_budget_ref(item) for item in protocol_items
        ],
        "protocol_required_preserved": all(
            item.id in kept_protocol_ids for item in protocol_items
        ),
        "source_tool_protocol_diagnostics": source_protocol_diagnostics,
        "tool_protocol_diagnostics": protocol_diagnostics,
        "tool_protocol_normalization": normalization_diagnostics,
        "orphan_tool_output_count": protocol_diagnostics.get(
            "orphan_tool_output_count",
        ),
        "missing_tool_output_count": protocol_diagnostics.get(
            "missing_tool_output_count",
        ),
        "duplicate_tool_call_id_count": protocol_diagnostics.get(
            "duplicate_tool_call_id_count",
        ),
    }
    return {key: value for key, value in report.items() if value not in (None, [], {})}


def session_item_frontier(
    items: tuple[SessionItem, ...],
) -> dict[str, object]:
    if not items:
        return {}
    return {
        "from_sequence_no": min(item.sequence_no for item in items),
        "to_sequence_no": max(item.sequence_no for item in items),
        "from_item_id": items[0].id,
        "to_item_id": items[-1].id,
        "item_count": len(items),
    }


__all__ = [
    "session_item_budget_report",
    "session_item_frontier",
    "truncate_items_to_recent_budget",
]
