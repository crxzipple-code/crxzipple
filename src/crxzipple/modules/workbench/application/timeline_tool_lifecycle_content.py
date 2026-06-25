from __future__ import annotations

import json
from typing import Any

from crxzipple.modules.llm.application.tool_result_model_text import (
    render_tool_result_model_text,
)
from crxzipple.modules.orchestration.domain.value_objects import ExecutionStepItemKind
from crxzipple.modules.tool.application.result_envelope import (
    TOOL_RESULT_ENVELOPE_METADATA_KEY,
)
from crxzipple.modules.tool.domain import ToolRun
from crxzipple.modules.workbench.application.execution_projection import (
    execution_item_view_status,
    summary_text,
)
from crxzipple.modules.workbench.application.projection_helpers import truncate


def timeline_content_for_tool_execution_item(
    item: Any,
    *,
    summary: dict[str, object],
    tool_name: str,
    tool_run: ToolRun | None = None,
) -> dict[str, Any]:
    content: dict[str, Any] = {
        "tool_name": tool_name,
    }
    tool_execution_plan = summary.get("tool_execution_plan")
    if isinstance(tool_execution_plan, dict) and tool_execution_plan:
        sanitized_plan = _timeline_tool_execution_plan(tool_execution_plan)
        if sanitized_plan:
            content["tool_execution_plan"] = sanitized_plan
    if item.kind is ExecutionStepItemKind.TOOL_CALL:
        content["text"] = f"Tool call requested: {tool_name}."
    elif item.kind is ExecutionStepItemKind.TOOL_RESULT:
        _apply_tool_result_content(
            content,
            summary=summary,
            tool_name=tool_name,
            tool_run=tool_run,
        )
    else:
        status = summary_text(summary, "status") or execution_item_view_status(item)
        content["text"] = f"Tool run {status}: {tool_name}."
    return content


def _apply_tool_result_content(
    content: dict[str, Any],
    *,
    summary: dict[str, object],
    tool_name: str,
    tool_run: ToolRun | None,
) -> None:
    result_session_item_id = summary_text(
        summary,
        "result_session_item_id",
    )
    result_summary = (
        summary_text(summary, "result_summary")
        or summary_text(summary, "summary")
        or summary_text(summary, "tool_result_summary")
    )
    exit_code = _summary_int(summary, "exit_code")
    truncated = _summary_optional_bool(summary, "truncated")
    output_truncated = _summary_optional_bool(summary, "output_truncated")
    read_handles = _summary_read_handles(summary)
    provider_visible_excerpt = _provider_visible_tool_result_excerpt(
        summary,
        tool_run=tool_run,
    )
    if result_summary:
        content["summary"] = result_summary
    if provider_visible_excerpt:
        content["provider_visible_excerpt"] = provider_visible_excerpt
        content["markdown"] = provider_visible_excerpt
    if exit_code is not None:
        content["exit_code"] = exit_code
    if truncated is not None:
        content["truncated"] = truncated
    elif output_truncated is not None:
        content["truncated"] = output_truncated
    if read_handles:
        content["read_handles"] = list(read_handles)
    elif tool_run is not None:
        tool_run_read_handles = _tool_run_read_handles(tool_run)
        if tool_run_read_handles:
            content["read_handles"] = list(tool_run_read_handles)
    suffix = f" Result item: {result_session_item_id}." if result_session_item_id else ""
    if result_summary:
        content["text"] = f"{result_summary}{suffix}"
    else:
        content["text"] = f"Tool result recorded for {tool_name}.{suffix}"


def _timeline_tool_execution_plan(
    plan: dict[str, object],
) -> dict[str, object]:
    sanitized: dict[str, object] = {}
    for key in _TIMELINE_TOOL_EXECUTION_PLAN_KEYS:
        value = plan.get(key)
        if isinstance(value, str) and value.strip():
            sanitized[key] = truncate(value, limit=240)
        elif isinstance(value, bool | int | float):
            sanitized[key] = value
    return sanitized


def _summary_int(summary: dict[str, object], key: str) -> int | None:
    value = summary.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _summary_optional_bool(summary: dict[str, object], key: str) -> bool | None:
    if key not in summary:
        return None
    value = summary.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str) and value.strip():
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return None


def _summary_read_handles(summary: dict[str, object]) -> tuple[dict[str, object], ...]:
    raw = summary.get("read_handles")
    if not isinstance(raw, list | tuple):
        raw = summary.get("tool_result_read_handles")
    if not isinstance(raw, list | tuple):
        return ()
    handles: list[dict[str, object]] = []
    for item in raw:
        if isinstance(item, dict):
            handles.append(dict(item))
        elif isinstance(item, str) and item.strip():
            handles.append({"id": item.strip()})
    return tuple(handles)


def _provider_visible_tool_result_excerpt(
    summary: dict[str, object],
    *,
    tool_run: ToolRun | None,
) -> str | None:
    if tool_run is not None:
        excerpt = render_tool_result_model_text(_tool_run_model_text_payload(tool_run))
        if excerpt is not None:
            return truncate(excerpt, limit=2400)
    summary_excerpt = _summary_tool_result_excerpt(summary)
    if summary_excerpt is not None:
        return truncate(summary_excerpt, limit=320)
    return None


def _tool_run_model_text_payload(tool_run: ToolRun) -> dict[str, object]:
    result = tool_run.result
    result_payload = result.to_payload() if result is not None else {}
    details = result.details if result is not None and isinstance(result.details, dict) else {}
    metadata = dict(result.metadata) if result is not None else {}
    envelope = dict(tool_run.result_envelope_payload or {})
    if envelope:
        metadata.setdefault(TOOL_RESULT_ENVELOPE_METADATA_KEY, envelope)
    return {
        "output_payload": tool_run.output_payload,
        "details": details,
        "metadata": metadata,
        "result_payload": result_payload,
    }


def _tool_run_read_handles(tool_run: ToolRun) -> tuple[dict[str, object], ...]:
    envelope = tool_run.result_envelope_payload
    if not isinstance(envelope, dict):
        return ()
    raw = envelope.get("read_handles")
    if not isinstance(raw, list):
        return ()
    return tuple(dict(item) for item in raw if isinstance(item, dict))


def _summary_tool_result_excerpt(summary: dict[str, object]) -> str | None:
    lines = ["tool_result:"]
    for label, key in (
        ("summary", "result_summary"),
        ("summary", "summary"),
        ("summary", "tool_result_summary"),
        ("exit_code", "exit_code"),
        ("stdout_excerpt", "stdout_excerpt"),
        ("stderr_excerpt", "stderr_excerpt"),
    ):
        value = summary_text(summary, key)
        if value is not None:
            lines.append(f"{label}: {truncate(value, limit=240)}")
    read_handles = _summary_read_handles(summary)
    if read_handles:
        lines.append(
            "read_handles: "
            + json.dumps(list(read_handles[:8]), ensure_ascii=True, sort_keys=True),
        )
    return "\n".join(lines) if len(lines) > 1 else None


_TIMELINE_TOOL_EXECUTION_PLAN_KEYS = {
    "tool_call_id",
    "tool_name",
    "tool_id",
    "execution_mode",
    "execution_strategy",
    "execution_environment",
    "arguments_digest",
    "input_digest",
    "risk",
    "approval_required",
}
