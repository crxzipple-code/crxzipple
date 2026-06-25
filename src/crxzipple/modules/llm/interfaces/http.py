from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse

from crxzipple.interfaces.authorization import authorize_llm_action
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.modules.llm.application import (
    WarmupLlmProfileInput,
)
from crxzipple.modules.llm.application.llm_profile_config import (
    register_llm_profile_input_from_config,
)
from crxzipple.modules.llm.domain.exceptions import LlmValidationError

from .http_request_mapping import (
    invoke_request_to_input,
    register_request_to_input,
    stream_request_to_input,
)
from .http_response_mapping import (
    to_invocation_llm_request_preview_response,
    to_invocation_response,
    to_profile_response,
)
from .http_sse import format_sse_event
from .http_models import (
    InvokeLlmRequest,
    LlmInvocationResponse,
    LlmInvocationRuntimeRequestPreviewResponse,
    LlmProfileResponse,
    RegisterLlmProfileRequest,
    TestLlmProfileRequest,
    WarmupLlmProfileResponse,
)


router = APIRouter()


@router.post("", response_model=LlmProfileResponse, status_code=status.HTTP_201_CREATED)
def register_profile(
    payload: RegisterLlmProfileRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> LlmProfileResponse:
    try:
        profile = container.require(AppKey.LLM_SERVICE).register_profile(
            register_request_to_input(payload),
        )
    except LlmValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "llm_profile_validation_failed",
                "message": str(exc),
            },
        ) from exc
    return to_profile_response(profile)


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
        to_profile_response(profile)
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
    return [to_profile_response(item) for item in synced]


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
            register_request_to_input(payload.profile),
            invoke_request_to_input(payload.profile.id, payload),
        )
    except LlmValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "llm_profile_validation_failed",
                "message": str(exc),
            },
        ) from exc
    return to_invocation_response(invocation)


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
        profile = container.require(AppKey.LLM_SERVICE).update_profile(
            register_request_to_input(payload),
        )
    except LlmValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "llm_profile_validation_failed",
                "message": str(exc),
            },
        ) from exc
    return to_profile_response(profile)


@router.get("/{llm_id}", response_model=LlmProfileResponse)
def get_profile(
    llm_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> LlmProfileResponse:
    return to_profile_response(container.require(AppKey.LLM_SERVICE).get_profile(llm_id))


@router.post("/{llm_id}/enable", response_model=LlmProfileResponse)
def enable_profile(
    llm_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> LlmProfileResponse:
    return to_profile_response(
        container.require(AppKey.LLM_SERVICE).set_profile_enabled(llm_id, enabled=True),
    )


@router.post("/{llm_id}/disable", response_model=LlmProfileResponse)
def disable_profile(
    llm_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> LlmProfileResponse:
    return to_profile_response(
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
        invoke_request_to_input(llm_id, payload),
    )
    return to_invocation_response(invocation)


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
            stream_request_to_input(llm_id, payload),
        ):
            yield format_sse_event(event.type, event.to_payload())

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@router.post("/{llm_id}/warmup", response_model=WarmupLlmProfileResponse)
def warmup_llm_profile(
    llm_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> WarmupLlmProfileResponse:
    authorize_llm_action(
        container,
        llm_id=llm_id,
        action="llm.warmup",
        interface_name="http",
    )
    result = container.require(AppKey.LLM_SERVICE).warmup_profile(
        WarmupLlmProfileInput(llm_id=llm_id),
    )
    return WarmupLlmProfileResponse(
        llm_id=result.llm_id,
        status=result.status,
        details=dict(result.details),
    )


@router.get("/{llm_id}/invocations", response_model=list[LlmInvocationResponse])
def list_invocations(
    llm_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    run_id: str | None = Query(default=None),
) -> list[LlmInvocationResponse]:
    return [
        to_invocation_response(invocation)
        for invocation in container.require(AppKey.LLM_SERVICE).list_invocations(
            llm_id=llm_id,
            run_id=run_id,
        )
    ]


@router.get("/calls/{invocation_id}", response_model=LlmInvocationResponse)
def get_invocation(
    invocation_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> LlmInvocationResponse:
    return to_invocation_response(
        container.require(AppKey.LLM_SERVICE).get_invocation(invocation_id),
    )


@router.get(
    "/calls/{invocation_id}/llm-request-preview",
    response_model=LlmInvocationRuntimeRequestPreviewResponse,
)
def get_invocation_llm_request_preview(
    invocation_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    run_id: str | None = Query(default=None),
) -> LlmInvocationRuntimeRequestPreviewResponse:
    invocation = container.require(AppKey.LLM_SERVICE).get_invocation(invocation_id)
    return to_invocation_llm_request_preview_response(invocation, run_id=run_id)
