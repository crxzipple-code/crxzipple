from __future__ import annotations

import json
from typing import Any

from crxzipple.modules.llm.domain import LlmInvocation
from crxzipple.modules.operations.application.read_models.llm_invocation_detail_common import (
    truncate,
)


def result_payload(invocation: LlmInvocation) -> dict[str, Any] | None:
    if invocation.result is None:
        return None
    return sanitize_payload(invocation.result.to_payload())


def result_summary(invocation: LlmInvocation) -> str:
    if invocation.result is None:
        return ""
    if invocation.result.text:
        return truncate(invocation.result.text, 240)
    if invocation.result.tool_calls:
        return f"{len(invocation.result.tool_calls)} tool calls"
    if invocation.result.structured_output is not None:
        return _json_preview(invocation.result.structured_output)
    if invocation.result.finish_reason:
        return invocation.result.finish_reason
    return ""


def sanitize_payload(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return truncate(value, 240)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return truncate(value, 512)
    if isinstance(value, dict):
        return {
            str(key): sanitize_payload(item, depth=depth + 1)
            for key, item in list(value.items())[:40]
            if isinstance(key, str)
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_payload(item, depth=depth + 1) for item in list(value)[:40]]
    return truncate(value, 240)


def _json_preview(value: Any) -> str:
    try:
        return truncate(
            json.dumps(sanitize_payload(value), ensure_ascii=False, sort_keys=True),
            240,
        )
    except TypeError:
        return truncate(value, 240)
