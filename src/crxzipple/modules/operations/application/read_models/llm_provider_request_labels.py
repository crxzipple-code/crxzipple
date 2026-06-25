from __future__ import annotations

from typing import Any

from crxzipple.modules.llm.domain import LlmInvocation
from crxzipple.modules.operations.application.read_models.llm_invocation_labels import (
    provider_request_preview,
)


def provider_request_continuation_label(invocation: LlmInvocation) -> str:
    preview = provider_request_preview(invocation)
    if not preview:
        return "-"
    has_previous = bool(preview.get("has_previous_response_id"))
    previous_response_id = _text(preview.get("previous_response_id"))
    if has_previous and previous_response_id:
        return f"previous_response_id={previous_response_id}"
    if has_previous:
        return "previous_response_id present"
    return "initial request"


def provider_request_transport_label(invocation: LlmInvocation) -> str:
    preview = provider_request_preview(invocation)
    value = _text(preview.get("transport"))
    return value or "-"


def provider_request_input_delta_label(invocation: LlmInvocation) -> str:
    preview = provider_request_preview(invocation)
    if not preview:
        return "-"
    delta_mode = preview.get("input_delta_mode")
    input_delta_count = preview.get("input_delta_count")
    input_baseline_count = preview.get("input_baseline_count")
    parts: list[str] = []
    if isinstance(delta_mode, bool):
        parts.append(f"mode={str(delta_mode).lower()}")
    if isinstance(input_delta_count, int):
        parts.append(f"delta={input_delta_count}")
    if isinstance(input_baseline_count, int):
        parts.append(f"baseline={input_baseline_count}")
    return "; ".join(parts) if parts else "-"


def provider_continuation_fallback_label(invocation: LlmInvocation) -> str:
    result = getattr(invocation, "result", None)
    metadata = getattr(result, "metadata", None)
    if not isinstance(metadata, dict):
        return "-"
    if metadata.get("provider_continuation_fallback") is not True:
        return "-"
    reason = _text(metadata.get("provider_continuation_fallback_reason"))
    return reason or "fallback"


def provider_request_input_items_label(invocation: LlmInvocation) -> str:
    preview = provider_request_preview(invocation)
    values = preview.get("input_item_types")
    if not isinstance(values, list) or not values:
        return "-"
    return ", ".join(str(item) for item in values[:8])


def provider_request_tool_count_label(invocation: LlmInvocation) -> str:
    preview = provider_request_preview(invocation)
    value = preview.get("tool_count")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return "-"


def provider_request_options_label(invocation: LlmInvocation) -> str:
    preview = provider_request_preview(invocation)
    option_summary = preview.get("option_summary")
    if not isinstance(option_summary, dict) or not option_summary:
        return "-"
    keys = [
        key
        for key, value in option_summary.items()
        if value not in (None, {}, [], ())
    ]
    if not keys:
        return "-"
    return ", ".join(str(key) for key in keys[:8])


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
