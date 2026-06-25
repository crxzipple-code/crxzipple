from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.presenters import (
    truncate_text,
)
from crxzipple.modules.tool.domain import ToolRun, ToolRunStatus
from crxzipple.shared.content_blocks import describe_content_for_text_fallback


def tool_run_result_summary(run: ToolRun) -> str:
    if run.error_message:
        return truncate_text(run.error_message, 96)
    payload = tool_run_result_payload(run)
    blocks = payload.get("content")
    if blocks:
        return truncate_text(describe_content_for_text_fallback(blocks), 96)
    details = payload.get("details")
    if details is not None:
        return truncate_text(_payload_summary(details), 96)
    if run.status is ToolRunStatus.SUCCEEDED:
        return "Completed"
    return "-"


def tool_run_result_payload(run: ToolRun) -> dict[str, Any]:
    payload = run.result_payload
    if isinstance(payload, dict):
        return payload
    return {}


def _payload_summary(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("output_text", "message", "summary", "text"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()
        return f"{len(value)} fields"
    if isinstance(value, list):
        return f"{len(value)} items"
    return str(value)
