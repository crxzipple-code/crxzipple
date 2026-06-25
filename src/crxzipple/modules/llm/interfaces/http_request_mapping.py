from __future__ import annotations

from crxzipple.modules.llm.application import (
    InvokeLlmInput,
    RegisterLlmProfileInput,
    StreamLlmInput,
)
from crxzipple.modules.llm.domain import (
    LlmDefaults,
    LlmInputItem,
    LlmInputItemKind,
    LlmMessage,
    LlmSourceKind,
    ToolSchema,
)

from .http_models import (
    InvokeLlmRequest,
    LlmInputItemRequest,
    LlmMessageRequest,
    RegisterLlmProfileRequest,
    ToolSchemaRequest,
)


def register_request_to_input(
    payload: RegisterLlmProfileRequest,
) -> RegisterLlmProfileInput:
    return RegisterLlmProfileInput(
        id=payload.id,
        provider=payload.provider,
        api_family=payload.api_family,
        model_name=payload.model_name,
        context_window_tokens=payload.context_window_tokens,
        model_family=payload.model_family,
        capabilities=tuple(payload.capabilities),
        default_params=LlmDefaults(
            temperature=payload.default_params.temperature,
            top_p=payload.default_params.top_p,
            max_output_tokens=payload.default_params.max_output_tokens,
            reasoning_effort=payload.default_params.reasoning_effort,
            provider_transport=payload.default_params.provider_transport,
            extra_body=dict(payload.default_params.extra_body),
        ),
        base_url=payload.base_url,
        credential_binding_id=payload.credential_binding_id,
        timeout_seconds=payload.timeout_seconds,
        max_concurrency=payload.max_concurrency,
        concurrency_key=payload.concurrency_key,
        source_kind=LlmSourceKind.MANUAL,
        enabled=payload.enabled,
    )


def invoke_request_to_input(
    llm_id: str,
    payload: InvokeLlmRequest,
) -> InvokeLlmInput:
    return InvokeLlmInput(
        llm_id=llm_id,
        messages=messages_from_request(payload.messages),
        input_items=input_items_from_request(payload.input_items),
        provider_context_messages=messages_from_request(
            payload.provider_context_messages,
        ),
        tool_schemas=tool_schemas_from_request(payload.tool_schemas),
        response_format=payload.response_format,
        overrides=payload.overrides,
        request_metadata=payload.request_metadata,
        invocation_id=payload.invocation_id,
    )


def stream_request_to_input(
    llm_id: str,
    payload: InvokeLlmRequest,
) -> StreamLlmInput:
    return StreamLlmInput(
        llm_id=llm_id,
        messages=messages_from_request(payload.messages),
        input_items=input_items_from_request(payload.input_items),
        provider_context_messages=messages_from_request(
            payload.provider_context_messages,
        ),
        tool_schemas=tool_schemas_from_request(payload.tool_schemas),
        response_format=payload.response_format,
        overrides=payload.overrides,
        request_metadata=payload.request_metadata,
        invocation_id=payload.invocation_id,
    )


def input_items_from_request(
    items: list[LlmInputItemRequest],
) -> tuple[LlmInputItem, ...]:
    return tuple(
        LlmInputItem(
            kind=LlmInputItemKind(item.kind),
            payload=item.payload,
            source=item.source,
            metadata=item.metadata,
        )
        for item in items
    )


def messages_from_request(
    messages: list[LlmMessageRequest],
) -> tuple[LlmMessage, ...]:
    return tuple(
        LlmMessage(
            role=item.role,
            content=item.content,
            name=item.name,
            tool_call_id=item.tool_call_id,
            metadata=item.metadata,
        )
        for item in messages
    )


def tool_schemas_from_request(
    tool_schemas: list[ToolSchemaRequest],
) -> tuple[ToolSchema, ...]:
    return tuple(
        ToolSchema(
            name=item.name,
            description=item.description,
            input_schema=item.input_schema,
        )
        for item in tool_schemas
    )


__all__ = [
    "input_items_from_request",
    "invoke_request_to_input",
    "messages_from_request",
    "register_request_to_input",
    "stream_request_to_input",
    "tool_schemas_from_request",
]
