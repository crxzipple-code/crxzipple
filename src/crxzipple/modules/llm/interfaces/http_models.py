from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmCapability,
    LlmMessageRole,
    LlmModelFamily,
    LlmProviderKind,
)


class LlmDefaultsResponse(BaseModel):
    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None
    reasoning_effort: str | None = None
    provider_transport: str | None = None
    extra_body: dict[str, Any] = Field(default_factory=dict)


class RegisterLlmProfileRequest(BaseModel):
    id: str
    provider: LlmProviderKind
    api_family: LlmApiFamily
    model_name: str
    context_window_tokens: int | None = None
    model_family: LlmModelFamily = LlmModelFamily.GENERAL
    capabilities: list[LlmCapability] = Field(default_factory=list)
    default_params: LlmDefaultsResponse = Field(default_factory=LlmDefaultsResponse)
    base_url: str | None = None
    credential_binding_id: str | None = None
    timeout_seconds: int = 60
    max_concurrency: int | None = Field(default=None, ge=1)
    concurrency_key: str | None = None
    enabled: bool = True
    reason: str | None = None


class LlmProfileResponse(BaseModel):
    id: str
    provider: str
    api_family: str
    model_name: str
    context_window_tokens: int | None = None
    model_family: str
    capabilities: list[str]
    default_params: LlmDefaultsResponse
    base_url: str | None
    credential_binding_id: str | None
    timeout_seconds: int
    max_concurrency: int | None = None
    concurrency_key: str | None = None
    source_kind: str
    enabled: bool


class WarmupLlmProfileResponse(BaseModel):
    llm_id: str
    status: str
    details: dict[str, Any] = Field(default_factory=dict)


class LlmMessageRequest(BaseModel):
    role: LlmMessageRole
    content: Any
    name: str | None = None
    tool_call_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LlmInputItemRequest(BaseModel):
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)
    source: str = "projection"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolSchemaRequest(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class InvokeLlmRequest(BaseModel):
    messages: list[LlmMessageRequest]
    input_items: list[LlmInputItemRequest] = Field(min_length=1)
    provider_context_messages: list[LlmMessageRequest] = Field(default_factory=list)
    tool_schemas: list[ToolSchemaRequest] = Field(default_factory=list)
    response_format: dict[str, Any] | None = None
    overrides: dict[str, Any] = Field(default_factory=dict)
    request_metadata: dict[str, Any] = Field(default_factory=dict)
    invocation_id: str | None = None


class TestLlmProfileRequest(BaseModel):
    profile: RegisterLlmProfileRequest
    messages: list[LlmMessageRequest]
    input_items: list[LlmInputItemRequest] = Field(min_length=1)
    provider_context_messages: list[LlmMessageRequest] = Field(default_factory=list)
    tool_schemas: list[ToolSchemaRequest] = Field(default_factory=list)
    response_format: dict[str, Any] | None = None
    overrides: dict[str, Any] = Field(default_factory=dict)
    request_metadata: dict[str, Any] = Field(default_factory=dict)
    invocation_id: str | None = None


class ToolCallIntentResponse(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]


class LlmUsageResponse(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None


class LlmResultResponse(BaseModel):
    text: str | None = None
    tool_calls: list[ToolCallIntentResponse] = Field(default_factory=list)
    structured_output: Any | None = None
    usage: LlmUsageResponse | None = None
    finish_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LlmErrorResponse(BaseModel):
    message: str
    code: str
    details: dict[str, Any] = Field(default_factory=dict)


class LlmInvocationResponse(BaseModel):
    id: str
    llm_id: str
    run_id: str | None = None
    agent_id: str | None = None
    session_key: str | None = None
    active_session_id: str | None = None
    messages: list[LlmMessageRequest]
    input_items: list[LlmInputItemRequest] = Field(default_factory=list)
    provider_context_messages: list[LlmMessageRequest] = Field(default_factory=list)
    tool_schemas: list[ToolSchemaRequest]
    response_format: dict[str, Any] | None = None
    request_overrides: dict[str, Any]
    request_metadata: dict[str, Any] = Field(default_factory=dict)
    provider_request_payload_preview: dict[str, Any] = Field(default_factory=dict)
    provider_render_report: dict[str, Any] = Field(default_factory=dict)
    provider_wire_preview: dict[str, Any] = Field(default_factory=dict)
    status: str
    result: LlmResultResponse | None = None
    response_items: list[dict[str, Any]] = Field(default_factory=list)
    error: LlmErrorResponse | None = None
    provider_request_id: str | None = None
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None


class LlmInvocationRuntimeRequestPreviewResponse(BaseModel):
    invocation_id: str
    run_id: str | None = None
    llm_id: str
    mode: str
    messages: list[LlmMessageRequest] = Field(default_factory=list)
    tool_schemas: list[ToolSchemaRequest] = Field(default_factory=list)
    runtime_request_report: dict[str, Any] | None = None
    request_render_snapshot_id: str | None = None
    request_render_snapshot: dict[str, Any] | None = None
    request_render_snapshot_metadata: dict[str, Any] = Field(default_factory=dict)
    provider_request_options: dict[str, Any] = Field(default_factory=dict)
