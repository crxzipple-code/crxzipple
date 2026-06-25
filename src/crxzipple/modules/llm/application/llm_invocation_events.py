from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crxzipple.modules.llm.application.llm_invocation_runtime_summary import (
    provider_context_message_kinds,
    runtime_request_summary,
)
from crxzipple.modules.llm.domain.entities import LlmInvocation, LlmProfile


def invocation_started_event_payload(
    invocation: LlmInvocation,
    profile: LlmProfile,
    *,
    streaming: bool,
) -> dict[str, Any]:
    return {
        "invocation_id": invocation.id,
        "llm_id": invocation.llm_id,
        "provider": profile.provider.value,
        "api_family": profile.api_family.value,
        "model_name": profile.model_name,
        "model_family": profile.model_family.value,
        "concurrency_key": profile.concurrency_key or f"profile:{profile.id}",
        "max_concurrency": profile.max_concurrency,
        "timeout_seconds": profile.timeout_seconds,
        "streaming": streaming,
        "message_count": len(invocation.messages),
        "input_item_count": len(invocation.input_items),
        "input_item_kinds": [item.kind.value for item in invocation.input_items],
        "provider_context_message_count": len(invocation.provider_context_messages),
        "provider_context_message_kinds": provider_context_message_kinds(
            invocation.provider_context_messages,
        ),
        "tool_schema_count": len(invocation.tool_schemas),
        "response_format_configured": invocation.response_format is not None,
        "runtime_request_summary": runtime_request_summary(invocation),
        "request_metadata": dict(invocation.request_metadata),
        **_runtime_reference_payload(invocation),
    }


def invocation_provider_request_prepared_event_payload(
    invocation: LlmInvocation,
    profile: LlmProfile | None,
) -> dict[str, Any]:
    preview = dict(invocation.provider_request_payload_preview)
    payload: dict[str, Any] = {
        "invocation_id": invocation.id,
        "llm_id": invocation.llm_id,
        "runtime_request_summary": runtime_request_summary(invocation),
        "request_metadata": dict(invocation.request_metadata),
        "provider_request_payload_preview": preview,
        **_runtime_reference_payload(invocation),
    }
    transport = preview.get("transport")
    if transport is not None:
        payload["transport"] = transport
    has_previous_response_id = preview.get("has_previous_response_id")
    if isinstance(has_previous_response_id, bool):
        payload["has_previous_response_id"] = has_previous_response_id
    input_delta_mode = preview.get("input_delta_mode")
    if isinstance(input_delta_mode, bool):
        payload["input_delta_mode"] = input_delta_mode
    for key in ("input_baseline_count", "input_delta_count", "tool_count"):
        value = preview.get(key)
        if isinstance(value, int):
            payload[key] = value
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


def profile_warmup_event_payload(
    profile: LlmProfile,
    *,
    status: str,
    details: Mapping[str, Any],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "llm_id": profile.id,
        "provider": profile.provider.value,
        "api_family": profile.api_family.value,
        "model_name": profile.model_name,
        "model_family": profile.model_family.value,
        "status": status,
        "details": dict(details),
    }
    transport = details.get("transport")
    if transport is not None:
        payload["transport"] = transport
    endpoint = details.get("endpoint")
    if endpoint is not None:
        payload["endpoint"] = endpoint
    reused_connection = details.get("reused_connection")
    if isinstance(reused_connection, bool):
        payload["reused_connection"] = reused_connection
    reason = details.get("reason")
    if reason is not None:
        payload["reason"] = str(reason)
    return payload


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
    "invocation_provider_request_prepared_event_payload",
    "invocation_started_event_payload",
    "profile_warmup_event_payload",
]
