from __future__ import annotations

from typing import Any


def timeline_source_refs(step: Any) -> dict[str, str]:
    refs: dict[str, str] = {}
    trace = step.trace
    if trace.run_id:
        refs["run_id"] = trace.run_id
    if trace.turn_id:
        refs["turn_id"] = trace.turn_id
    if trace.source_event_id:
        refs["source_event_id"] = trace.source_event_id
    if trace.source_owner:
        refs["source_owner"] = trace.source_owner
    if trace.source_event_name:
        refs["source_event_name"] = trace.source_event_name
    if trace.session_item_id:
        refs["session_item_id"] = trace.session_item_id
    if trace.step_id:
        refs["execution_step_id"] = trace.step_id
    execution_item_id = execution_item_id_from_step_id(step.step_id)
    if execution_item_id is not None:
        refs["execution_item_id"] = execution_item_id
    if trace.llm_invocation_id:
        refs["llm_invocation_id"] = trace.llm_invocation_id
    if trace.request_render_snapshot_id:
        refs["request_render_snapshot_id"] = trace.request_render_snapshot_id
    if trace.tool_run_id:
        refs["tool_run_id"] = trace.tool_run_id
    if trace.artifact_id:
        refs["artifact_id"] = trace.artifact_id
    if trace.approval_request_id:
        refs["approval_request_id"] = trace.approval_request_id
    return refs


def execution_item_id_from_step_id(step_id: str) -> str | None:
    marker = ":item-"
    if marker not in step_id:
        return None
    return step_id.rsplit(":", 1)[-1] or None


def timeline_ref(item: Any, key: str) -> str | None:
    if key == "tool_call_id":
        return (
            item.source_refs.get("tool_call_id")
            or item.source_refs.get("call_id")
            or getattr(item.trace, "tool_call_id", None)
        )
    return item.source_refs.get(key) or getattr(item.trace, key, None)


def timeline_sort_key(item: Any) -> tuple[str, str, str]:
    return (
        item.started_at or "",
        item.source_refs.get("execution_step_id", ""),
        item.id,
    )


def first_timeline_timestamp(items: tuple[Any, ...]) -> str | None:
    for item in items:
        if item.started_at:
            return item.started_at
    return None


def last_timeline_timestamp(items: tuple[Any, ...]) -> str | None:
    for item in reversed(items):
        if item.completed_at or item.started_at:
            return item.completed_at or item.started_at
    return None
