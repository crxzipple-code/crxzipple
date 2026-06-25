from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.orchestration.domain import ExecutionOwnerReference
from crxzipple.modules.operations.application.read_models.routes import (
    workbench_trace_route,
)
from crxzipple.modules.tool.domain import ToolRun
from crxzipple.shared.time import format_datetime_utc


def tool_run_contexts(
    run_query: Any | None,
    runs: list[ToolRun],
) -> dict[str, dict[str, str]]:
    if run_query is None or not hasattr(run_query, "find_execution_step_items_by_owner"):
        return {}
    contexts: dict[str, dict[str, str]] = {}
    for run in runs:
        context = execution_owner_context(
            run_query,
            ExecutionOwnerReference(owner_kind="tool_run", owner_id=run.id),
        )
        if not context:
            continue
        existing = contexts.get(run.id)
        if existing is None or context.get("updated_at", "") > existing.get("updated_at", ""):
            contexts[run.id] = context
    return {
        run_id: {
            key: value
            for key, value in context.items()
            if key != "updated_at"
        }
        for run_id, context in contexts.items()
    }


def execution_owner_context(
    run_query: Any,
    owner: ExecutionOwnerReference,
) -> dict[str, str] | None:
    try:
        items = run_query.find_execution_step_items_by_owner(owner)
    except Exception:
        return None
    if not items:
        return None
    item = max(items, key=_execution_item_updated_at)
    try:
        step = run_query.get_execution_step(item.step_id)
    except Exception:
        step = None
    try:
        run = run_query.get_run(item.turn_id)
    except Exception:
        run = None
    run_id = _optional_text(getattr(run, "id", None)) or _optional_text(
        getattr(item, "turn_id", None),
    )
    if run_id is None:
        return None
    metadata = getattr(run, "metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    trace_id = _optional_text(metadata.get("trace_id")) or run_id
    summary_payload = item.summary_payload if isinstance(item.summary_payload, dict) else {}
    tool_call_id = _optional_text(item.correlation_key) or _optional_text(
        summary_payload.get("tool_call_id"),
    )
    owner_ref = getattr(item, "owner", None)
    owner_tool_run_id = (
        _optional_text(getattr(owner_ref, "owner_id", None))
        if _optional_text(getattr(owner_ref, "owner_kind", None)) == "tool_run"
        else None
    )
    focus_id = (
        owner_tool_run_id
        or _optional_text(summary_payload.get("tool_run_id"))
        or tool_call_id
        or _optional_text(getattr(item, "id", None))
    )
    return {
        "run_id": run_id,
        "turn_id": _optional_text(metadata.get("turn_id")) or item.turn_id,
        "trace_id": trace_id,
        "session_key": _optional_text(metadata.get("session_key")) or "-",
        "route": f"/ui/workbench/runs/{run_id}",
        "trace_route": workbench_trace_route(trace_id, focus_id=focus_id),
        "chain_id": item.chain_id,
        "step_id": item.step_id,
        "step_kind": _enum_value(getattr(step, "kind", None)),
        "step_status": _enum_value(getattr(step, "status", None)),
        "item_status": _enum_value(getattr(item, "status", None)),
        "tool_call_id": tool_call_id or "-",
        "updated_at": _execution_item_updated_at(item),
    }


def _execution_item_updated_at(item: Any) -> str:
    updated_at = getattr(item, "updated_at", None)
    if isinstance(updated_at, datetime):
        return format_datetime_utc(updated_at)
    return str(updated_at or "")


def _enum_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    if raw is None:
        return "-"
    normalized = str(raw).strip()
    return normalized or "-"


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
