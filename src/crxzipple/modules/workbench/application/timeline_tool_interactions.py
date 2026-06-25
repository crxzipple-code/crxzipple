from __future__ import annotations

from dataclasses import replace
from typing import Any

from crxzipple.modules.workbench.application import view_models as models
from crxzipple.modules.workbench.application.projection_helpers import truncate
from crxzipple.modules.workbench.application.timeline_refs import (
    first_timeline_timestamp,
    last_timeline_timestamp,
    timeline_ref,
    timeline_sort_key,
)


def merge_tool_interaction_timeline_items(
    items: tuple[Any, ...],
) -> tuple[Any, ...]:
    groups: dict[str, list[Any]] = {}
    ungrouped: list[Any] = []
    for item in items:
        tool_call_id = timeline_ref(item, "tool_call_id")
        if item.kind in {"tool_call", "tool_run", "tool_result"} and tool_call_id:
            groups.setdefault(tool_call_id, []).append(item)
        else:
            ungrouped.append(item)

    merged: list[Any] = []
    for tool_call_id, group_items in groups.items():
        if len(group_items) <= 1:
            merged.extend(group_items)
            continue
        merged.append(
            _merge_tool_interaction_group(
                tool_call_id=tool_call_id,
                items=tuple(sorted(group_items, key=timeline_sort_key)),
            ),
        )
    return tuple(
        sorted(
            (*ungrouped, *merged),
            key=timeline_sort_key,
        ),
    )


def _merge_tool_interaction_group(
    *,
    tool_call_id: str,
    items: tuple[Any, ...],
) -> Any:
    primary = _primary_tool_interaction_item(items)
    source_refs = dict(primary.source_refs)
    for item in items:
        for key, value in item.source_refs.items():
            source_refs.setdefault(key, value)
    source_refs["tool_call_id"] = tool_call_id
    tool_name = _tool_interaction_name(items)
    lifecycle = tuple(_tool_interaction_lifecycle_entry(item) for item in items)
    content = dict(primary.content)
    content.update(
        {
            "tool_name": tool_name,
            "text": _tool_interaction_text(items, tool_name=tool_name),
            "lifecycle": list(lifecycle),
            "lifecycle_item_count": len(lifecycle),
        },
    )
    content.update(_tool_interaction_result_content(items))
    tool_execution_plan = _tool_interaction_plan(items)
    if tool_execution_plan is not None:
        content["tool_execution_plan"] = tool_execution_plan
    return models.WorkbenchTimelineItem(
        id=f"timeline:{primary.run_id}:tool-interaction:{tool_call_id}",
        turn_id=primary.turn_id,
        run_id=primary.run_id,
        kind="tool_call",
        status=_tool_interaction_status(items),
        title=f"Tool Interaction: {tool_name}",
        content=content,
        phase=primary.phase,
        source_refs=source_refs,
        started_at=first_timeline_timestamp(items),
        completed_at=last_timeline_timestamp(items),
        trace=_merged_tool_interaction_trace(primary.trace, source_refs),
    )


def _merged_tool_interaction_trace(trace: Any, source_refs: dict[str, str]) -> Any:
    return replace(
        trace,
        execution_item_id=source_refs.get("execution_item_id") or trace.execution_item_id,
        tool_run_id=source_refs.get("tool_run_id") or trace.tool_run_id,
        tool_call_id=source_refs.get("tool_call_id") or trace.tool_call_id,
        llm_invocation_id=source_refs.get("llm_invocation_id")
        or trace.llm_invocation_id,
        llm_response_item_id=source_refs.get("llm_response_item_id")
        or trace.llm_response_item_id,
        request_render_snapshot_id=source_refs.get("request_render_snapshot_id")
        or trace.request_render_snapshot_id,
        session_item_id=source_refs.get("session_item_id") or trace.session_item_id,
    )


def _primary_tool_interaction_item(items: tuple[Any, ...]) -> Any:
    for item in items:
        if item.kind == "tool_call" and item.source_refs.get("llm_response_item_id"):
            return item
    for item in items:
        if item.kind == "tool_call":
            return item
    return items[0]


def _tool_interaction_name(items: tuple[Any, ...]) -> str:
    for item in items:
        name = item.content.get("tool_name") or item.source_refs.get("tool_id")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return "tool"


def _tool_interaction_plan(items: tuple[Any, ...]) -> dict[str, Any] | None:
    for item in items:
        plan = item.content.get("tool_execution_plan")
        if isinstance(plan, dict) and plan:
            return dict(plan)
    return None


def _tool_interaction_result_content(items: tuple[Any, ...]) -> dict[str, Any]:
    result_content: dict[str, Any] = {}
    for item in items:
        if item.kind != "tool_result":
            continue
        for key in (
            "summary",
            "provider_visible_excerpt",
            "markdown",
            "exit_code",
            "truncated",
            "read_handles",
        ):
            value = item.content.get(key)
            if value not in (None, "", [], {}):
                result_content.setdefault(key, value)
    return result_content


def _tool_interaction_status(items: tuple[Any, ...]) -> str:
    statuses = {item.status for item in items}
    if statuses & {"failed", "error", "cancelled"}:
        return "failed"
    if statuses & {"waiting", "running", "queued"}:
        return "running"
    if "success" in statuses or "completed" in statuses:
        return "success"
    return items[-1].status


def _tool_interaction_text(items: tuple[Any, ...], *, tool_name: str) -> str:
    status = _tool_interaction_status(items)
    if status == "failed":
        return f"Tool interaction failed: {tool_name}."
    if status == "running":
        return f"Tool interaction running: {tool_name}."
    return f"Tool interaction completed: {tool_name}."


def _tool_interaction_lifecycle_entry(item: Any) -> dict[str, Any]:
    return {
        "id": item.id,
        "kind": item.kind,
        "status": item.status,
        "title": item.title,
        "source_refs": _tool_interaction_lifecycle_source_refs(item.source_refs),
        "started_at": item.started_at,
        "completed_at": item.completed_at,
        "content": _tool_interaction_lifecycle_content(item.content),
    }


def _tool_interaction_lifecycle_source_refs(
    source_refs: dict[str, str],
) -> dict[str, str]:
    compact: dict[str, str] = {}
    for key in (
        "execution_item_id",
        "tool_run_id",
        "session_item_id",
        "request_render_snapshot_id",
    ):
        value = source_refs.get(key)
        if isinstance(value, str) and value.strip():
            compact[key] = value.strip()
    return compact


def _tool_interaction_lifecycle_content(content: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key in (
        "tool_name",
        "text",
        "summary",
        "exit_code",
        "truncated",
        "read_handles",
        "tool_execution_plan",
    ):
        value = content.get(key)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, str):
            compact[key] = truncate(value, limit=240)
        elif isinstance(value, dict):
            compact[key] = dict(value)
        elif isinstance(value, list):
            compact[key] = list(value[:8])
        else:
            compact[key] = value
    return compact
