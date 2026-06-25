from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crxzipple.modules.llm.application.runtime_input_items import (
    runtime_input_items_from_projected_payloads,
)
from crxzipple.modules.llm.domain import LlmInputItem


def filter_runtime_input_items_for_request_render_snapshot(
    input_items: tuple[LlmInputItem, ...],
    snapshot: Any | None,
) -> tuple[tuple[LlmInputItem, ...], dict[str, object]]:
    before_count = len(input_items)
    filtered, orphan_report = _drop_unpaired_function_call_items(input_items)
    mode = (
        "request_render_projected_input"
        if snapshot is not None and getattr(snapshot, "projected_input_items", ())
        else "unfiltered"
    )
    return filtered, {
        "mode": mode,
        "input_before_filter_count": before_count,
        "input_after_filter_count": len(filtered),
        "dropped_input_item_count": before_count - len(filtered),
        **orphan_report,
    }


def runtime_input_items_from_request_render_snapshot(
    snapshot: Any | None,
) -> tuple[LlmInputItem, ...]:
    projected_input_items = (
        getattr(snapshot, "projected_input_items", ()) if snapshot is not None else ()
    )
    if not projected_input_items:
        return ()
    return runtime_input_items_from_projected_payloads(
        tuple(raw for raw in projected_input_items if isinstance(raw, Mapping)),
        default_source="context_slice",
    )


def request_render_context_source(snapshot: Any | None) -> str | None:
    metadata = getattr(snapshot, "metadata", None) if snapshot is not None else None
    if not isinstance(metadata, Mapping):
        return None
    value = metadata.get("request_context_source")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _drop_unpaired_function_call_items(
    input_items: tuple[LlmInputItem, ...],
) -> tuple[tuple[LlmInputItem, ...], dict[str, object]]:
    call_ids = {
        call_id
        for item in input_items
        if item.kind == "function_call"
        and (call_id := _input_item_tool_call_id(item)) is not None
    }
    output_call_ids = {
        call_id
        for item in input_items
        if item.kind == "function_call_output"
        and (call_id := _input_item_tool_call_id(item)) is not None
    }
    dropped_calls = tuple(
        item
        for item in input_items
        if item.kind == "function_call"
        and _input_item_tool_call_id(item) not in output_call_ids
    )
    dropped_outputs = tuple(
        item
        for item in input_items
        if item.kind == "function_call_output"
        and _input_item_tool_call_id(item) not in call_ids
    )
    dropped = (*dropped_calls, *dropped_outputs)
    kept = tuple(item for item in input_items if item not in dropped)
    if not dropped:
        return input_items, {"dropped_orphan_function_call_count": 0}
    report = {
        "dropped_orphan_function_call_count": len(dropped_calls),
        "dropped_orphan_function_call_ids": [
            call_id
            for item in dropped_calls
            if (call_id := _input_item_tool_call_id(item)) is not None
        ],
    }
    if dropped_outputs:
        report["dropped_orphan_function_call_output_count"] = len(dropped_outputs)
        report["dropped_orphan_function_call_output_ids"] = [
            call_id
            for item in dropped_outputs
            if (call_id := _input_item_tool_call_id(item)) is not None
        ]
    return kept, report


def _input_item_tool_call_id(item: LlmInputItem) -> str | None:
    metadata = item.metadata if isinstance(item.metadata, Mapping) else {}
    payload = item.payload if isinstance(item.payload, Mapping) else {}
    return _first_text(
        metadata.get("tool_call_id"),
        metadata.get("call_id"),
        payload.get("tool_call_id"),
        payload.get("call_id"),
    )


def _first_text(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
