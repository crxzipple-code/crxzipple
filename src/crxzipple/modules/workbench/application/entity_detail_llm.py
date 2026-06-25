from __future__ import annotations

from crxzipple.modules.workbench.application.entity_detail_llm_provider import (
    llm_provider_input_summary_payload,
    llm_provider_render_report,
    llm_provider_wire_preview,
    llm_runtime_observations_payload,
)
from crxzipple.modules.workbench.application.entity_detail_llm_replay import (
    llm_replay_input_payload,
)
from crxzipple.modules.workbench.application.entity_detail_values import (
    enum_or_text,
    iso_or_none,
    optional_dict,
)


def llm_invocation_detail_payload(invocation: object) -> dict[str, object]:
    result = getattr(invocation, "result", None)
    error = getattr(invocation, "error", None)
    request_metadata = dict(getattr(invocation, "request_metadata", {}) or {})
    provider_request_preview = optional_dict(
        getattr(invocation, "provider_request_payload_preview", None),
    ) or {}
    return {
        "id": getattr(invocation, "id", None),
        "kind": "llm_invocation",
        "llm_id": getattr(invocation, "llm_id", None),
        "status": enum_or_text(getattr(invocation, "status", None)),
        "started_at": iso_or_none(getattr(invocation, "started_at", None)),
        "completed_at": iso_or_none(getattr(invocation, "completed_at", None)),
        "message_count": len(tuple(getattr(invocation, "messages", ()) or ())),
        "tool_schema_count": len(tuple(getattr(invocation, "tool_schemas", ()) or ())),
        "request_metadata": request_metadata,
        "provider_request_payload_preview": provider_request_preview,
        "provider_render_report": llm_provider_render_report(provider_request_preview),
        "provider_wire_preview": llm_provider_wire_preview(provider_request_preview),
        "replay_input": llm_replay_input_payload(invocation),
        "provider_input_summary": llm_provider_input_summary_payload(
            request_metadata,
            provider_request_preview,
        ),
        "runtime_observations": llm_runtime_observations_payload(
            provider_request_preview,
        ),
        "result_summary": _llm_result_summary(result, error=error),
        "result_payload": result.to_payload() if result is not None else None,
        "error": error.to_payload() if error is not None else None,
    }


def _llm_result_summary(result: object | None, *, error: object | None) -> str:
    if error is not None:
        message = getattr(error, "message", None)
        return str(message or "LLM invocation failed.")
    if result is None:
        return "LLM invocation has no result yet."
    text = getattr(result, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()[:240]
    tool_calls = getattr(result, "tool_calls", None)
    if isinstance(tool_calls, list | tuple) and tool_calls:
        return f"{len(tool_calls)} tool calls"
    finish_reason = getattr(result, "finish_reason", None)
    return str(finish_reason or "LLM invocation completed.")
