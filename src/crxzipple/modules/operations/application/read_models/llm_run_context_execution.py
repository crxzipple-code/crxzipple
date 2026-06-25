from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.orchestration.domain import ExecutionOwnerReference
from crxzipple.modules.operations.application.read_models.routes import (
    workbench_trace_route,
)
from crxzipple.shared.time import format_datetime_utc


def execution_owner_context(run_query: Any, invocation_id: str) -> dict[str, str] | None:
    try:
        items = run_query.find_execution_step_items_by_owner(
            ExecutionOwnerReference(
                owner_kind="llm_invocation",
                owner_id=invocation_id,
            ),
        )
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
    run_id = _text(getattr(run, "id", None)) or _text(getattr(item, "turn_id", None))
    if run_id is None:
        return None
    metadata = getattr(run, "metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    trace_id = _text(metadata.get("trace_id")) or run_id
    summary_payload = item.summary_payload if isinstance(item.summary_payload, dict) else {}
    focus_id = (
        _text(getattr(item, "correlation_key", None))
        or _text(summary_payload.get("llm_invocation_id"))
        or _text(summary_payload.get("invocation_id"))
        or _text(getattr(item, "id", None))
    )
    return {
        "run_id": run_id,
        "turn_id": _text(metadata.get("turn_id")) or item.turn_id,
        "trace_id": trace_id,
        "session_key": _text(metadata.get("session_key")) or "-",
        "route": f"/ui/workbench/runs/{run_id}",
        "trace_route": workbench_trace_route(trace_id, focus_id=focus_id),
        "chain_id": item.chain_id,
        "step_id": item.step_id,
        "step_kind": _enum_value(getattr(step, "kind", None)),
        "step_status": _enum_value(getattr(step, "status", None)),
        "item_status": _enum_value(getattr(item, "status", None)),
        **_llm_execution_summary_context(getattr(item, "summary_payload", None)),
        "updated_at": _execution_item_updated_at(item),
    }


def _llm_execution_summary_context(summary_payload: Any) -> dict[str, str]:
    if not isinstance(summary_payload, dict):
        return {}
    progress_ids = _text_list(summary_payload.get("assistant_progress_item_ids"))
    result: dict[str, str] = {}
    if progress_ids:
        result["assistant_progress_item_ids"] = ", ".join(progress_ids)
        result["assistant_progress_item_count"] = str(len(progress_ids))
    progress_text = _text(summary_payload.get("assistant_progress_text"))
    if progress_text is not None:
        result["assistant_progress_text"] = _truncate(progress_text, 160)
    tool_call_names = _text_list(summary_payload.get("tool_call_names"))
    if tool_call_names:
        result["tool_call_names"] = ", ".join(tool_call_names)
        result["tool_call_count"] = str(len(tool_call_names))
    return result


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


def _text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def _text_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    items: list[str] = []
    for item in value:
        text = _text(item)
        if text is not None:
            items.append(text)
    return tuple(items)


def _truncate(value: Any, limit: int = 160) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."
