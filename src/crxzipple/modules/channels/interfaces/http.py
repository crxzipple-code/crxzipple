from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.channels.domain import (
    ChannelProfile,
    ChannelValidationError,
    channel_connection_control_topic,
)
from crxzipple.modules.channels.interfaces.http_dead_letters import (
    router as dead_letters_router,
)
from crxzipple.modules.channels.interfaces.http_lark_events import (
    router as lark_events_router,
)
from crxzipple.modules.channels.interfaces.http_webhook_inbound import (
    router as webhook_inbound_router,
)
from crxzipple.modules.channels.interfaces.http_web_events import (
    router as web_events_router,
)
from crxzipple.modules.channels.interfaces.http_models import (
    ChannelAccountBindingResponse,
    ChannelConnectionBindingResponse,
    ChannelProfileResponse,
    ChannelProfileUpsertRequest,
    ChannelRuntimeDetailResponse,
    ChannelRuntimeSummaryResponse,
    WebChannelSubscriptionResponse,
    WebChannelSubscriptionUpdateRequest,
)
from crxzipple.modules.events import Event


router = APIRouter()
router.include_router(dead_letters_router)
router.include_router(lark_events_router)
router.include_router(webhook_inbound_router)
router.include_router(web_events_router)


def _channel_profile_response(profile: ChannelProfile) -> ChannelProfileResponse:
    payload = profile.to_payload()
    return ChannelProfileResponse(
        channel_type=str(payload["channel_type"]),
        enabled=bool(payload["enabled"]),
        capabilities=dict(payload["capabilities"]),
        accounts=list(payload["accounts"]),
        metadata=dict(payload["metadata"]),
    )


def _runtime_summary_response(
    *,
    container: AppContainer,
    runtime,
) -> ChannelRuntimeSummaryResponse:
    account_bindings = container.require(AppKey.CHANNEL_RUNTIME_MANAGER).list_account_bindings(
        runtime_id=runtime.runtime_id,
    )
    connection_bindings = container.require(AppKey.CHANNEL_RUNTIME_MANAGER).list_connection_bindings(
        runtime_id=runtime.runtime_id,
    )
    return ChannelRuntimeSummaryResponse(
        runtime_id=runtime.runtime_id,
        channel_type=runtime.channel_type,
        service_key=runtime.service_key,
        status=runtime.status,
        registered_at=runtime.registered_at.isoformat(),
        last_heartbeat_at=runtime.last_heartbeat_at.isoformat(),
        account_count=len(account_bindings),
        connection_count=len(connection_bindings),
    )


@router.get("/profiles")
def list_channel_profiles(
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[ChannelProfileResponse]:
    return [
        _channel_profile_response(profile)
        for profile in container.require(AppKey.CHANNEL_PROFILE_SERVICE).list_profiles()
    ]


@router.get("/profiles/{channel_type}")
def get_channel_profile(
    channel_type: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ChannelProfileResponse:
    profile = container.require(AppKey.CHANNEL_PROFILE_SERVICE).get_profile(channel_type)
    if profile is None:
        raise HTTPException(status_code=404, detail="Channel profile not found.")
    return _channel_profile_response(profile)


@router.put("/profiles/{channel_type}")
def upsert_channel_profile(
    channel_type: str,
    payload: ChannelProfileUpsertRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ChannelProfileResponse:
    normalized_channel = channel_type.strip().lower()
    if not normalized_channel:
        raise HTTPException(status_code=400, detail="channel_type is required.")
    payload_channel = (
        payload.channel_type.strip().lower()
        if isinstance(payload.channel_type, str) and payload.channel_type.strip()
        else normalized_channel
    )
    if payload_channel != normalized_channel:
        raise HTTPException(
            status_code=400,
            detail="channel_type in path and payload must match.",
        )
    try:
        profile = ChannelProfile.from_payload(
            {
                "channel_type": normalized_channel,
                "enabled": payload.enabled,
                "capabilities": dict(payload.capabilities),
                "accounts": [dict(item) for item in payload.accounts],
                "metadata": dict(payload.metadata),
            },
        )
        saved = container.require(AppKey.CHANNEL_PROFILE_SERVICE).upsert_profile(profile)
    except (ChannelValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _channel_profile_response(saved)


@router.post("/profiles/{channel_type}/enable")
def enable_channel_profile(
    channel_type: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ChannelProfileResponse:
    try:
        profile = container.require(AppKey.CHANNEL_PROFILE_SERVICE).enable_profile(channel_type)
    except ChannelValidationError as exc:
        raise HTTPException(
            status_code=404 if exc.code == "channel_profile_not_found" else 400,
            detail=exc.to_payload() if exc.has_payload else str(exc),
        ) from exc
    return _channel_profile_response(profile)


@router.post("/profiles/{channel_type}/disable")
def disable_channel_profile(
    channel_type: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ChannelProfileResponse:
    try:
        profile = container.require(AppKey.CHANNEL_PROFILE_SERVICE).disable_profile(channel_type)
    except ChannelValidationError as exc:
        raise HTTPException(
            status_code=404 if exc.code == "channel_profile_not_found" else 400,
            detail=exc.to_payload() if exc.has_payload else str(exc),
        ) from exc
    return _channel_profile_response(profile)


@router.delete("/profiles/{channel_type}")
def remove_channel_profile(
    channel_type: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[ChannelProfileResponse]:
    config = container.require(AppKey.CHANNEL_PROFILE_SERVICE).remove_profile(channel_type)
    return [_channel_profile_response(profile) for profile in config.profiles]


@router.get("/runtimes")
def list_channel_runtimes(
    container: Annotated[AppContainer, Depends(get_container)],
    channel_type: str | None = Query(default=None),
) -> list[ChannelRuntimeSummaryResponse]:
    runtimes = container.require(AppKey.CHANNEL_RUNTIME_MANAGER).list_runtimes(
        channel_type=channel_type,
    )
    return [
        _runtime_summary_response(container=container, runtime=runtime)
        for runtime in runtimes
    ]


@router.get("/runtimes/{runtime_id}")
def get_channel_runtime(
    runtime_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ChannelRuntimeDetailResponse:
    runtime = container.require(AppKey.CHANNEL_RUNTIME_MANAGER).get_runtime(runtime_id)
    if runtime is None:
        raise HTTPException(status_code=404, detail="Channel runtime not found.")
    account_bindings = container.require(AppKey.CHANNEL_RUNTIME_MANAGER).list_account_bindings(
        runtime_id=runtime.runtime_id,
    )
    connection_bindings = container.require(AppKey.CHANNEL_RUNTIME_MANAGER).list_connection_bindings(
        runtime_id=runtime.runtime_id,
    )
    return ChannelRuntimeDetailResponse(
        runtime_id=runtime.runtime_id,
        channel_type=runtime.channel_type,
        service_key=runtime.service_key,
        status=runtime.status,
        capabilities=runtime.capabilities.to_payload(),
        metadata=dict(runtime.metadata),
        registered_at=runtime.registered_at.isoformat(),
        last_heartbeat_at=runtime.last_heartbeat_at.isoformat(),
        account_bindings=[
            ChannelAccountBindingResponse(
                channel_type=item.channel_type,
                channel_account_id=item.channel_account_id,
                runtime_id=item.runtime_id,
                updated_at=item.updated_at.isoformat(),
                metadata=dict(item.metadata),
            )
            for item in account_bindings
        ],
        connection_bindings=[
            ChannelConnectionBindingResponse(
                channel_type=item.channel_type,
                connection_id=item.connection_id,
                runtime_id=item.runtime_id,
                channel_account_id=item.channel_account_id,
                conversation_id=item.conversation_id,
                supports_streaming=item.supports_streaming,
                updated_at=item.updated_at.isoformat(),
                metadata=dict(item.metadata),
            )
            for item in connection_bindings
        ],
    )


@router.post("/web/connections/{connection_id}/subscription")
def update_web_channel_subscription(
    connection_id: str,
    payload: WebChannelSubscriptionUpdateRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> WebChannelSubscriptionResponse:
    normalized_connection_id = connection_id.strip()
    if not normalized_connection_id:
        raise HTTPException(status_code=400, detail="connection_id is required.")
    normalized_conversation_id = (
        payload.conversation_id.strip()
        if isinstance(payload.conversation_id, str) and payload.conversation_id.strip()
        else None
    )
    normalized_channel_account_id = (
        payload.channel_account_id.strip()
        if isinstance(payload.channel_account_id, str) and payload.channel_account_id.strip()
        else "default"
    )
    existing_binding = container.require(AppKey.CHANNEL_RUNTIME_MANAGER).resolve_connection_binding(
        channel_type="web",
        connection_id=normalized_connection_id,
    )
    previous_conversation_id = (
        existing_binding.conversation_id
        if existing_binding is not None
        else None
    )
    binding = container.require(AppKey.CHANNEL_RUNTIME_MANAGER).update_connection_subscription(
        channel_type="web",
        connection_id=normalized_connection_id,
        conversation_id=normalized_conversation_id,
    )
    if binding is None:
        runtime = container.require(AppKey.CHANNEL_RUNTIME_MANAGER).resolve_account_runtime(
            channel_type="web",
            channel_account_id=normalized_channel_account_id,
        )
        binding = container.require(AppKey.WEB_CHANNEL_RUNTIME_SERVICE).bind_connection(
            connection_id=normalized_connection_id,
            channel_account_id=normalized_channel_account_id,
            conversation_id=normalized_conversation_id,
            supports_streaming=True,
            runtime_id=runtime.runtime_id if runtime is not None else "web-runtime-1",
            metadata={},
        )
    conversation_changed = (
        (previous_conversation_id or None) != (binding.conversation_id or None)
    )
    if conversation_changed and binding.conversation_id:
        binding = (
            container.require(AppKey.WEB_CHANNEL_RUNTIME_SERVICE).ensure_connection_source_cursors(
                connection_id=binding.connection_id,
                conversation_id=binding.conversation_id,
            )
            or binding
        )
    if conversation_changed or existing_binding is None:
        container.require(AppKey.EVENTS_SERVICE).publish(
            Event(
                topic=channel_connection_control_topic(
                    "web",
                    connection_id=binding.connection_id,
                ),
                kind="control",
                ordering_key=binding.connection_id,
                payload={
                    "event_name": "channel.connection.subscription_updated",
                    "channel_type": "web",
                    "channel_account_id": binding.channel_account_id,
                    "connection_id": binding.connection_id,
                    "conversation_id": binding.conversation_id,
                    "runtime_id": binding.runtime_id,
                },
            )
        )
    return WebChannelSubscriptionResponse(
        runtime_id=binding.runtime_id,
        channel_account_id=binding.channel_account_id,
        connection_id=binding.connection_id,
        conversation_id=binding.conversation_id,
        supports_streaming=binding.supports_streaming,
        updated_at=binding.updated_at.isoformat(),
        metadata=dict(binding.metadata),
    )
