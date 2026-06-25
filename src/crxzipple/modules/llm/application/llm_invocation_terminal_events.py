from __future__ import annotations

from typing import Any

from crxzipple.modules.llm.application.adapters import LlmAdapterResponse
from crxzipple.modules.llm.application.error_classification import (
    llm_error_family,
    llm_error_retryable,
)
from crxzipple.modules.llm.domain.entities import LlmInvocation, LlmProfile
from crxzipple.modules.llm.domain import LlmErrorPayload, LlmResult


def invocation_succeeded_event_payload(
    invocation: LlmInvocation,
    profile: LlmProfile | None,
    *,
    streaming: bool,
) -> dict[str, Any]:
    payload = invocation_terminal_base_payload(
        invocation,
        profile,
        streaming=streaming,
    )
    if invocation.result is not None:
        response_text = invocation.result.text or ""
        payload["finish_reason"] = invocation.result.finish_reason
        payload["text_present"] = bool(response_text.strip())
        payload["text_chars"] = len(response_text)
        payload["tool_call_count"] = len(invocation.result.tool_calls)
        if invocation.result.tool_calls:
            payload["tool_call_names"] = [
                tool_call.name for tool_call in invocation.result.tool_calls
            ]
        if invocation.result.usage is not None:
            payload["usage"] = invocation.result.usage.to_payload()
    return payload


def invocation_failed_event_payload(
    invocation: LlmInvocation,
    profile: LlmProfile | None,
    *,
    error: LlmErrorPayload,
    streaming: bool,
) -> dict[str, Any]:
    payload = invocation_terminal_base_payload(
        invocation,
        profile,
        streaming=streaming,
    )
    payload.update(
        {
            "error_code": error.code,
            "error_family": llm_error_family(error.code),
            "retryable": llm_error_retryable(error.code),
            "error_message": error.message,
        },
    )
    if error.details:
        payload["error_details"] = dict(error.details)
    return payload


def invocation_terminal_base_payload(
    invocation: LlmInvocation,
    profile: LlmProfile | None,
    *,
    streaming: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "invocation_id": invocation.id,
        "llm_id": invocation.llm_id,
        "provider_request_id": invocation.provider_request_id,
        "duration_seconds": invocation_duration_seconds(invocation),
        "streaming": streaming,
        "request_metadata": dict(invocation.request_metadata),
        "provider_request_payload_preview": dict(
            invocation.provider_request_payload_preview,
        ),
        **_runtime_reference_payload(invocation),
    }
    if profile is not None:
        payload.update(
            {
                "provider": profile.provider.value,
                "api_family": profile.api_family.value,
                "model_name": profile.model_name,
                "model_family": profile.model_family.value,
                "concurrency_key": profile.concurrency_key or f"profile:{profile.id}",
            },
        )
    return payload


def result_summary_from_adapter_response(
    response: LlmAdapterResponse,
) -> LlmResult:
    if not response.response_items:
        return response.result
    return LlmResult.from_response_items(
        response.response_items,
        usage=response.result.usage,
        finish_reason=response.result.finish_reason,
        metadata=response.result.metadata,
        structured_output=response.result.structured_output,
    )


def invocation_duration_seconds(invocation: LlmInvocation) -> float | None:
    if invocation.started_at is None or invocation.completed_at is None:
        return None
    return max((invocation.completed_at - invocation.started_at).total_seconds(), 0.0)


def _runtime_reference_payload(invocation: LlmInvocation) -> dict[str, str]:
    payload: dict[str, str] = {}
    for key, value in {
        "run_id": invocation.run_id,
        "agent_id": invocation.agent_id,
        "session_key": invocation.session_key,
        "active_session_id": invocation.active_session_id,
    }.items():
        if value is not None:
            payload[key] = value
    return payload


__all__ = [
    "invocation_failed_event_payload",
    "invocation_succeeded_event_payload",
    "invocation_terminal_base_payload",
    "result_summary_from_adapter_response",
]
