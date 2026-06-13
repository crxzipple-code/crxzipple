from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.interfaces.authorization import authorize_llm_action
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.llm.application import (
    InvokeLlmInput,
    RegisterLlmProfileInput,
    StreamLlmInput,
)
from crxzipple.modules.llm.application.services import register_llm_profile_input_from_config
from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmCapability,
    LlmDefaults,
    LlmMessage,
    LlmMessageRole,
    LlmModelFamily,
    LlmProviderKind,
    LlmSourceKind,
    ToolSchema,
)
from crxzipple.modules.llm.domain.exceptions import LlmValidationError
from crxzipple.shared.time import (
    format_datetime_utc,
    format_optional_datetime_utc,
)


router = APIRouter()


class LlmDefaultsResponse(BaseModel):
    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None
    reasoning_effort: str | None = None
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


class LlmMessageRequest(BaseModel):
    role: LlmMessageRole
    content: Any
    name: str | None = None
    tool_call_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolSchemaRequest(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class InvokeLlmRequest(BaseModel):
    messages: list[LlmMessageRequest]
    tool_schemas: list[ToolSchemaRequest] = Field(default_factory=list)
    response_format: dict[str, Any] | None = None
    overrides: dict[str, Any] = Field(default_factory=dict)
    request_metadata: dict[str, Any] = Field(default_factory=dict)
    invocation_id: str | None = None


class TestLlmProfileRequest(BaseModel):
    profile: RegisterLlmProfileRequest
    messages: list[LlmMessageRequest]
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
    messages: list[LlmMessageRequest]
    tool_schemas: list[ToolSchemaRequest]
    response_format: dict[str, Any] | None = None
    request_overrides: dict[str, Any]
    request_metadata: dict[str, Any] = Field(default_factory=dict)
    provider_request_payload_preview: dict[str, Any] = Field(default_factory=dict)
    status: str
    result: LlmResultResponse | None = None
    response_items: list[dict[str, Any]] = Field(default_factory=list)
    error: LlmErrorResponse | None = None
    provider_request_id: str | None = None
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None


class LlmInvocationPromptPreviewResponse(BaseModel):
    invocation_id: str
    run_id: str | None = None
    llm_id: str
    mode: str
    messages: list[LlmMessageRequest] = Field(default_factory=list)
    tool_schemas: list[ToolSchemaRequest] = Field(default_factory=list)
    prompt_report: dict[str, Any] | None = None
    context_render_snapshot_id: str | None = None
    context_render: dict[str, Any] | None = None
    context_render_metadata: dict[str, Any] = Field(default_factory=dict)
    provider_attachments: dict[str, Any] = Field(default_factory=dict)
    provider_request_options: dict[str, Any] = Field(default_factory=dict)


@router.post("", response_model=LlmProfileResponse, status_code=status.HTTP_201_CREATED)
def register_profile(
    payload: RegisterLlmProfileRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> LlmProfileResponse:
    try:
        profile = container.require(AppKey.LLM_SERVICE).register_profile(_register_request_to_input(payload))
    except LlmValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "llm_profile_validation_failed",
                "message": str(exc),
            },
        ) from exc
    return _to_profile_response(profile)


def _register_request_to_input(
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


def _profile_config_id(config: object) -> str:
    if isinstance(config, Mapping):
        profile_id = config.get("profile_id")
        if profile_id is not None:
            return str(profile_id)
        return str(config.get("id"))
    profile_id = getattr(config, "profile_id", None)
    if profile_id is not None:
        return str(profile_id)
    return str(getattr(config, "id"))


def _configured_profiles_from_settings(container: AppContainer) -> tuple[object, ...]:
    return tuple(getattr(container.require(AppKey.CORE_SETTINGS), "llm_profiles", ()))


@router.get("", response_model=list[LlmProfileResponse])
def list_profiles(
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[LlmProfileResponse]:
    return [
        _to_profile_response(profile)
        for profile in container.require(AppKey.LLM_SERVICE).list_profiles()
    ]


@router.post("/sync-profiles", response_model=list[LlmProfileResponse])
def sync_profiles(
    container: Annotated[AppContainer, Depends(get_container)],
    profile: Annotated[list[str] | None, Query()] = None,
) -> list[LlmProfileResponse]:
    selected_ids = set(profile or [])
    configured_profiles = tuple(
        item
        for item in _configured_profiles_from_settings(container)
        if not selected_ids or _profile_config_id(item) in selected_ids
    )
    synced = container.require(AppKey.LLM_SERVICE).sync_profiles(
        tuple(
            register_llm_profile_input_from_config(item) for item in configured_profiles
        ),
    )
    return [_to_profile_response(item) for item in synced]


@router.post(
    "/test",
    response_model=LlmInvocationResponse,
    status_code=status.HTTP_201_CREATED,
)
def test_profile(
    payload: TestLlmProfileRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> LlmInvocationResponse:
    try:
        invocation = container.require(AppKey.LLM_SERVICE).test_profile(
            _register_request_to_input(payload.profile),
            InvokeLlmInput(
                llm_id=payload.profile.id,
                messages=tuple(
                    LlmMessage(
                        role=item.role,
                        content=item.content,
                        name=item.name,
                        tool_call_id=item.tool_call_id,
                        metadata=item.metadata,
                    )
                    for item in payload.messages
                ),
                tool_schemas=tuple(
                    ToolSchema(
                        name=item.name,
                        description=item.description,
                        input_schema=item.input_schema,
                    )
                    for item in payload.tool_schemas
                ),
                response_format=payload.response_format,
                overrides=payload.overrides,
                request_metadata=payload.request_metadata,
                invocation_id=payload.invocation_id,
            ),
        )
    except LlmValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "llm_profile_validation_failed",
                "message": str(exc),
            },
        ) from exc
    return _to_invocation_response(invocation)


@router.put("/{llm_id}", response_model=LlmProfileResponse)
def update_profile(
    llm_id: str,
    payload: RegisterLlmProfileRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> LlmProfileResponse:
    if payload.id != llm_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "llm_profile_id_mismatch",
                "message": "Request body id must match the llm_id path parameter.",
            },
        )
    try:
        profile = container.require(AppKey.LLM_SERVICE).update_profile(_register_request_to_input(payload))
    except LlmValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "llm_profile_validation_failed",
                "message": str(exc),
            },
        ) from exc
    return _to_profile_response(profile)


@router.get("/{llm_id}", response_model=LlmProfileResponse)
def get_profile(
    llm_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> LlmProfileResponse:
    return _to_profile_response(container.require(AppKey.LLM_SERVICE).get_profile(llm_id))


@router.post("/{llm_id}/enable", response_model=LlmProfileResponse)
def enable_profile(
    llm_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> LlmProfileResponse:
    return _to_profile_response(
        container.require(AppKey.LLM_SERVICE).set_profile_enabled(llm_id, enabled=True),
    )


@router.post("/{llm_id}/disable", response_model=LlmProfileResponse)
def disable_profile(
    llm_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> LlmProfileResponse:
    return _to_profile_response(
        container.require(AppKey.LLM_SERVICE).set_profile_enabled(llm_id, enabled=False),
    )


@router.delete("/{llm_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(
    llm_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> Response:
    container.require(AppKey.LLM_SERVICE).delete_profile(llm_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{llm_id}/invoke",
    response_model=LlmInvocationResponse,
    status_code=status.HTTP_201_CREATED,
)
def invoke_llm(
    llm_id: str,
    payload: InvokeLlmRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> LlmInvocationResponse:
    authorize_llm_action(
        container,
        llm_id=llm_id,
        action="llm.invoke",
        interface_name="http",
    )
    invocation = container.require(AppKey.LLM_SERVICE).invoke(
        InvokeLlmInput(
            llm_id=llm_id,
            messages=tuple(
                LlmMessage(
                    role=item.role,
                    content=item.content,
                    name=item.name,
                    tool_call_id=item.tool_call_id,
                    metadata=item.metadata,
                )
                for item in payload.messages
            ),
            tool_schemas=tuple(
                ToolSchema(
                    name=item.name,
                    description=item.description,
                    input_schema=item.input_schema,
                )
                for item in payload.tool_schemas
            ),
            response_format=payload.response_format,
            overrides=payload.overrides,
            request_metadata=payload.request_metadata,
            invocation_id=payload.invocation_id,
        ),
    )
    return _to_invocation_response(invocation)


@router.post("/{llm_id}/stream")
def stream_llm(
    llm_id: str,
    payload: InvokeLlmRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> StreamingResponse:
    authorize_llm_action(
        container,
        llm_id=llm_id,
        action="llm.stream",
        interface_name="http",
    )

    def event_stream():
        for event in container.require(AppKey.LLM_SERVICE).stream_invoke(
            StreamLlmInput(
                llm_id=llm_id,
                messages=tuple(
                    LlmMessage(
                        role=item.role,
                        content=item.content,
                        name=item.name,
                        tool_call_id=item.tool_call_id,
                        metadata=item.metadata,
                    )
                    for item in payload.messages
                ),
                tool_schemas=tuple(
                    ToolSchema(
                        name=item.name,
                        description=item.description,
                        input_schema=item.input_schema,
                    )
                    for item in payload.tool_schemas
                ),
                response_format=payload.response_format,
                overrides=payload.overrides,
                request_metadata=payload.request_metadata,
                invocation_id=payload.invocation_id,
            ),
        ):
            yield _format_sse_event(event.type, event.to_payload())

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/{llm_id}/invocations", response_model=list[LlmInvocationResponse])
def list_invocations(
    llm_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[LlmInvocationResponse]:
    return [
        _to_invocation_response(invocation)
        for invocation in container.require(AppKey.LLM_SERVICE).list_invocations(llm_id=llm_id)
    ]


@router.get("/calls/{invocation_id}", response_model=LlmInvocationResponse)
def get_invocation(
    invocation_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> LlmInvocationResponse:
    return _to_invocation_response(container.require(AppKey.LLM_SERVICE).get_invocation(invocation_id))


@router.get(
    "/calls/{invocation_id}/prompt-preview",
    response_model=LlmInvocationPromptPreviewResponse,
)
def get_invocation_prompt_preview(
    invocation_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    run_id: str | None = Query(default=None),
) -> LlmInvocationPromptPreviewResponse:
    invocation = container.require(AppKey.LLM_SERVICE).get_invocation(invocation_id)
    return _to_invocation_prompt_preview_response(invocation, run_id=run_id)


def _format_sse_event(event_name: str, payload: dict[str, Any]) -> str:
    return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _to_profile_response(profile: Any) -> LlmProfileResponse:
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


def _to_invocation_response(invocation: Any) -> LlmInvocationResponse:
    return LlmInvocationResponse(
        id=invocation.id,
        llm_id=invocation.llm_id,
        messages=[
            LlmMessageRequest(
                role=item.role,
                content=item.content,
                name=item.name,
                tool_call_id=item.tool_call_id,
                metadata=dict(item.metadata),
            )
            for item in invocation.messages
        ],
        tool_schemas=[
            ToolSchemaRequest(
                name=item.name,
                description=item.description,
                input_schema=dict(item.input_schema),
            )
            for item in invocation.tool_schemas
        ],
        response_format=(
            dict(invocation.response_format)
            if invocation.response_format is not None
            else None
        ),
        request_overrides=dict(invocation.request_overrides),
        request_metadata=dict(invocation.request_metadata),
        provider_request_payload_preview=dict(
            invocation.provider_request_payload_preview,
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


def _to_invocation_prompt_preview_response(
    invocation: Any,
    *,
    run_id: str | None,
) -> LlmInvocationPromptPreviewResponse:
    request_metadata = dict(invocation.request_metadata)
    context_render_snapshot_id = _optional_metadata_string(
        request_metadata.get("context_render_snapshot_id"),
    )
    mode = _optional_metadata_string(request_metadata.get("prompt_mode")) or "unknown"
    return LlmInvocationPromptPreviewResponse(
        invocation_id=invocation.id,
        run_id=run_id,
        llm_id=invocation.llm_id,
        mode=mode,
        messages=[
            LlmMessageRequest(
                role=item.role,
                content=item.content,
                name=item.name,
                tool_call_id=item.tool_call_id,
                metadata=dict(item.metadata),
            )
            for item in invocation.messages
        ],
        tool_schemas=[
            ToolSchemaRequest(
                name=item.name,
                description=item.description,
                input_schema=dict(item.input_schema),
            )
            for item in invocation.tool_schemas
        ],
        prompt_report=None,
        context_render_snapshot_id=context_render_snapshot_id,
        context_render=None,
        context_render_metadata={},
        provider_attachments={},
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


def _optional_metadata_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
