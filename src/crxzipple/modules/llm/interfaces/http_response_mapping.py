from __future__ import annotations

from typing import Any

from crxzipple.modules.llm.application.runtime_request_preview import (
    request_metadata_preview_payload,
)
from crxzipple.modules.llm.domain import LlmMessage, ToolSchema
from crxzipple.shared.time import (
    format_datetime_utc,
    format_optional_datetime_utc,
)

from .http_models import (
    LlmDefaultsResponse,
    LlmErrorResponse,
    LlmInputItemRequest,
    LlmInvocationResponse,
    LlmInvocationRuntimeRequestPreviewResponse,
    LlmMessageRequest,
    LlmProfileResponse,
    LlmResultResponse,
    LlmUsageResponse,
    ToolCallIntentResponse,
    ToolSchemaRequest,
)


def to_profile_response(profile: Any) -> LlmProfileResponse:
    return LlmProfileResponse(
        id=profile.id,
        provider=profile.provider.value,
        api_family=profile.api_family.value,
        model_name=profile.model_name,
        context_window_tokens=profile.context_window_tokens,
        model_family=profile.model_family.value,
        capabilities=[item.value for item in profile.capabilities],
        default_params=LlmDefaultsResponse(
            temperature=profile.default_params.temperature,
            top_p=profile.default_params.top_p,
            max_output_tokens=profile.default_params.max_output_tokens,
            reasoning_effort=profile.default_params.reasoning_effort,
            provider_transport=profile.default_params.provider_transport,
            extra_body=dict(profile.default_params.extra_body),
        ),
        base_url=profile.base_url,
        credential_binding_id=profile.credential_binding_id,
        timeout_seconds=profile.timeout_seconds,
        max_concurrency=profile.max_concurrency,
        concurrency_key=profile.concurrency_key,
        source_kind=profile.source_kind.value,
        enabled=profile.enabled,
    )


def to_invocation_response(invocation: Any) -> LlmInvocationResponse:
    provider_request_payload_preview = dict(
        invocation.provider_request_payload_preview,
    )
    return LlmInvocationResponse(
        id=invocation.id,
        llm_id=invocation.llm_id,
        run_id=invocation.run_id,
        agent_id=invocation.agent_id,
        session_key=invocation.session_key,
        active_session_id=invocation.active_session_id,
        messages=[
            message_request_from_value(item) for item in invocation.messages
        ],
        input_items=[
            LlmInputItemRequest(
                kind=item.kind.value,
                payload=dict(item.payload),
                source=item.source,
                metadata=dict(item.metadata),
            )
            for item in invocation.input_items
        ],
        provider_context_messages=[
            message_request_from_value(item)
            for item in invocation.provider_context_messages
        ],
        tool_schemas=[
            tool_schema_request_from_value(item) for item in invocation.tool_schemas
        ],
        response_format=(
            dict(invocation.response_format)
            if invocation.response_format is not None
            else None
        ),
        request_overrides=dict(invocation.request_overrides),
        request_metadata=dict(invocation.request_metadata),
        provider_request_payload_preview=provider_request_payload_preview,
        provider_render_report=provider_render_report(
            provider_request_payload_preview,
        ),
        provider_wire_preview=provider_wire_preview(
            provider_request_payload_preview,
        ),
        status=invocation.status.value,
        result=(
            LlmResultResponse(
                text=invocation.result.text,
                tool_calls=[
                    ToolCallIntentResponse(
                        id=item.id,
                        name=item.name,
                        arguments=dict(item.arguments),
                    )
                    for item in invocation.result.tool_calls
                ],
                structured_output=invocation.result.structured_output,
                usage=(
                    LlmUsageResponse(
                        input_tokens=invocation.result.usage.input_tokens,
                        output_tokens=invocation.result.usage.output_tokens,
                        total_tokens=invocation.result.usage.total_tokens,
                        reasoning_tokens=invocation.result.usage.reasoning_tokens,
                    )
                    if invocation.result.usage is not None
                    else None
                ),
                finish_reason=invocation.result.finish_reason,
                metadata=dict(invocation.result.metadata),
            )
            if invocation.result is not None
            else None
        ),
        response_items=[item.to_payload() for item in invocation.response_items],
        error=(
            LlmErrorResponse(
                message=invocation.error.message,
                code=invocation.error.code,
                details=dict(invocation.error.details),
            )
            if invocation.error is not None
            else None
        ),
        provider_request_id=invocation.provider_request_id,
        created_at=format_datetime_utc(invocation.created_at),
        started_at=format_optional_datetime_utc(invocation.started_at),
        completed_at=format_optional_datetime_utc(invocation.completed_at),
    )


def provider_render_report(preview: dict[str, Any]) -> dict[str, Any]:
    render_report = preview.get("render_report")
    return dict(render_report) if isinstance(render_report, dict) else {}


def provider_wire_preview(preview: dict[str, Any]) -> dict[str, Any]:
    wire_preview = dict(preview)
    wire_preview.pop("render_report", None)
    return wire_preview


def to_invocation_llm_request_preview_response(
    invocation: Any,
    *,
    run_id: str | None,
) -> LlmInvocationRuntimeRequestPreviewResponse:
    request_metadata = request_metadata_preview_payload(invocation.request_metadata)
    request_render_snapshot_id = optional_metadata_string(
        request_metadata.get("request_render_snapshot_id"),
    )
    mode = (
        optional_metadata_string(request_metadata.get("runtime_request_mode"))
        or "unknown"
    )
    return LlmInvocationRuntimeRequestPreviewResponse(
        invocation_id=invocation.id,
        run_id=run_id,
        llm_id=invocation.llm_id,
        mode=mode,
        messages=[
            message_request_from_value(item) for item in invocation.messages
        ],
        tool_schemas=[
            tool_schema_request_from_value(item) for item in invocation.tool_schemas
        ],
        runtime_request_report=None,
        request_render_snapshot_id=request_render_snapshot_id,
        request_render_snapshot=None,
        request_render_snapshot_metadata={},
        provider_request_options={
            "response_format": (
                dict(invocation.response_format)
                if invocation.response_format is not None
                else None
            ),
            "output_schema": None,
            "overrides": dict(invocation.request_overrides),
            "request_metadata": request_metadata,
            "invocation_id": invocation.id,
            "status": invocation.status.value,
            "provider_request_id": invocation.provider_request_id,
            "request_source": "llm_invocation",
        },
    )


def message_request_from_value(message: LlmMessage) -> LlmMessageRequest:
    return LlmMessageRequest(
        role=message.role,
        content=message.content,
        name=message.name,
        tool_call_id=message.tool_call_id,
        metadata=dict(message.metadata),
    )


def tool_schema_request_from_value(tool_schema: ToolSchema) -> ToolSchemaRequest:
    return ToolSchemaRequest(
        name=tool_schema.name,
        description=tool_schema.description,
        input_schema=dict(tool_schema.input_schema),
    )


def optional_metadata_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


__all__ = [
    "message_request_from_value",
    "optional_metadata_string",
    "provider_render_report",
    "provider_wire_preview",
    "to_invocation_llm_request_preview_response",
    "to_invocation_response",
    "to_profile_response",
    "tool_schema_request_from_value",
]
