from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.llm.domain.entities import LlmInvocation, LlmProfile
from crxzipple.modules.llm.domain.value_objects import (
    LlmDefaults,
    LlmErrorPayload,
    LlmMessage,
    LlmResult,
    LlmUsage,
    ToolCallIntent,
    ToolSchema,
)
from crxzipple.shared.time import (
    format_datetime_utc,
    format_optional_datetime_utc,
)


@dataclass(frozen=True, slots=True)
class LlmDefaultsDTO:
    temperature: float | None
    top_p: float | None
    max_output_tokens: int | None
    reasoning_effort: str | None
    extra_body: dict[str, object]

    @classmethod
    def from_value(cls, defaults: LlmDefaults) -> "LlmDefaultsDTO":
        return cls(
            temperature=defaults.temperature,
            top_p=defaults.top_p,
            max_output_tokens=defaults.max_output_tokens,
            reasoning_effort=defaults.reasoning_effort,
            extra_body=dict(defaults.extra_body),
        )


@dataclass(frozen=True, slots=True)
class LlmProfileDTO:
    id: str
    provider: str
    api_family: str
    model_name: str
    context_window_tokens: int | None
    model_family: str
    capabilities: tuple[str, ...]
    default_params: LlmDefaultsDTO
    base_url: str | None
    credential_binding: str | None
    timeout_seconds: int
    max_concurrency: int | None
    concurrency_key: str | None
    source_kind: str
    enabled: bool

    @classmethod
    def from_entity(cls, profile: LlmProfile) -> "LlmProfileDTO":
        return cls(
            id=profile.id,
            provider=profile.provider.value,
            api_family=profile.api_family.value,
            model_name=profile.model_name,
            context_window_tokens=profile.context_window_tokens,
            model_family=profile.model_family.value,
            capabilities=tuple(item.value for item in profile.capabilities),
            default_params=LlmDefaultsDTO.from_value(profile.default_params),
            base_url=profile.base_url,
            credential_binding=profile.credential_binding,
            timeout_seconds=profile.timeout_seconds,
            max_concurrency=profile.max_concurrency,
            concurrency_key=profile.concurrency_key,
            source_kind=profile.source_kind.value,
            enabled=profile.enabled,
        )


@dataclass(frozen=True, slots=True)
class LlmMessageDTO:
    role: str
    content: object
    name: str | None
    tool_call_id: str | None
    metadata: dict[str, object]

    @classmethod
    def from_value(cls, message: LlmMessage) -> "LlmMessageDTO":
        return cls(
            role=message.role.value,
            content=message.content,
            name=message.name,
            tool_call_id=message.tool_call_id,
            metadata=dict(message.metadata),
        )


@dataclass(frozen=True, slots=True)
class ToolSchemaDTO:
    name: str
    description: str
    input_schema: dict[str, object]

    @classmethod
    def from_value(cls, tool_schema: ToolSchema) -> "ToolSchemaDTO":
        return cls(
            name=tool_schema.name,
            description=tool_schema.description,
            input_schema=dict(tool_schema.input_schema),
        )


@dataclass(frozen=True, slots=True)
class ToolCallIntentDTO:
    id: str
    name: str
    arguments: dict[str, object]

    @classmethod
    def from_value(cls, tool_call: ToolCallIntent) -> "ToolCallIntentDTO":
        return cls(
            id=tool_call.id,
            name=tool_call.name,
            arguments=dict(tool_call.arguments),
        )


@dataclass(frozen=True, slots=True)
class LlmUsageDTO:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    reasoning_tokens: int | None

    @classmethod
    def from_value(cls, usage: LlmUsage) -> "LlmUsageDTO":
        return cls(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            reasoning_tokens=usage.reasoning_tokens,
        )


@dataclass(frozen=True, slots=True)
class LlmResultDTO:
    text: str | None
    tool_calls: tuple[ToolCallIntentDTO, ...]
    structured_output: object | None
    usage: LlmUsageDTO | None
    finish_reason: str | None
    metadata: dict[str, object]

    @classmethod
    def from_value(cls, result: LlmResult) -> "LlmResultDTO":
        return cls(
            text=result.text,
            tool_calls=tuple(
                ToolCallIntentDTO.from_value(item) for item in result.tool_calls
            ),
            structured_output=result.structured_output,
            usage=LlmUsageDTO.from_value(result.usage) if result.usage else None,
            finish_reason=result.finish_reason,
            metadata=dict(result.metadata),
        )


@dataclass(frozen=True, slots=True)
class LlmErrorDTO:
    message: str
    code: str
    details: dict[str, object]

    @classmethod
    def from_value(cls, error: LlmErrorPayload) -> "LlmErrorDTO":
        return cls(
            message=error.message,
            code=error.code,
            details=dict(error.details),
        )


@dataclass(frozen=True, slots=True)
class LlmInvocationDTO:
    id: str
    llm_id: str
    messages: tuple[LlmMessageDTO, ...]
    tool_schemas: tuple[ToolSchemaDTO, ...]
    response_format: dict[str, object] | None
    request_overrides: dict[str, object]
    status: str
    result: LlmResultDTO | None
    error: LlmErrorDTO | None
    provider_request_id: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None

    @classmethod
    def from_entity(cls, invocation: LlmInvocation) -> "LlmInvocationDTO":
        return cls(
            id=invocation.id,
            llm_id=invocation.llm_id,
            messages=tuple(
                LlmMessageDTO.from_value(item) for item in invocation.messages
            ),
            tool_schemas=tuple(
                ToolSchemaDTO.from_value(item) for item in invocation.tool_schemas
            ),
            response_format=(
                dict(invocation.response_format)
                if invocation.response_format is not None
                else None
            ),
            request_overrides=dict(invocation.request_overrides),
            status=invocation.status.value,
            result=(
                LlmResultDTO.from_value(invocation.result)
                if invocation.result is not None
                else None
            ),
            error=(
                LlmErrorDTO.from_value(invocation.error)
                if invocation.error is not None
                else None
            ),
            provider_request_id=invocation.provider_request_id,
            created_at=format_datetime_utc(invocation.created_at),
            started_at=format_optional_datetime_utc(invocation.started_at),
            completed_at=format_optional_datetime_utc(invocation.completed_at),
        )
