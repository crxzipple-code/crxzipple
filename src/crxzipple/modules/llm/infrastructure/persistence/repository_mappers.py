from __future__ import annotations

from crxzipple.modules.llm.domain.entities import LlmInvocation, LlmProfile
from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmCapability,
    LlmContinuationSignal,
    LlmDefaults,
    LlmErrorPayload,
    LlmInputItem,
    LlmInvocationStatus,
    LlmMessage,
    LlmMessagePhase,
    LlmMessageRole,
    LlmModelFamily,
    LlmProviderKind,
    LlmResponseEvent,
    LlmResponseEventType,
    LlmResponseItem,
    LlmResponseItemKind,
    LlmResult,
    LlmSourceKind,
    ToolSchema,
)
from crxzipple.modules.llm.infrastructure.persistence.models import (
    LlmInvocationModel,
    LlmInvocationResponseEventModel,
    LlmInvocationResponseItemModel,
    LlmProfileModel,
)
from crxzipple.shared.time import (
    coerce_optional_utc_datetime,
    coerce_utc_datetime,
)


def profile_to_model(profile: LlmProfile) -> LlmProfileModel:
    return LlmProfileModel(
        id=profile.id,
        provider=profile.provider.value,
        api_family=profile.api_family.value,
        model_name=profile.model_name,
        context_window_tokens=profile.context_window_tokens,
        model_family=profile.model_family.value,
        capabilities=[item.value for item in profile.capabilities],
        default_params=profile.default_params.to_payload(),
        base_url=profile.base_url,
        credential_binding_id=profile.credential_binding_id,
        timeout_seconds=profile.timeout_seconds,
        max_concurrency=profile.max_concurrency,
        concurrency_key=profile.concurrency_key,
        source_kind=profile.source_kind.value,
        enabled=profile.enabled,
    )


def profile_from_model(model: LlmProfileModel) -> LlmProfile:
    return LlmProfile(
        id=model.id,
        provider=LlmProviderKind(model.provider),
        api_family=LlmApiFamily(model.api_family),
        model_name=model.model_name,
        context_window_tokens=model.context_window_tokens,
        model_family=LlmModelFamily(model.model_family),
        capabilities=tuple(LlmCapability(item) for item in (model.capabilities or [])),
        default_params=LlmDefaults.from_payload(model.default_params),
        base_url=model.base_url,
        credential_binding_id=model.credential_binding_id,
        timeout_seconds=model.timeout_seconds,
        max_concurrency=model.max_concurrency,
        concurrency_key=model.concurrency_key,
        source_kind=LlmSourceKind(model.source_kind),
        enabled=model.enabled,
    )


def invocation_to_model(invocation: LlmInvocation) -> LlmInvocationModel:
    return LlmInvocationModel(
        id=invocation.id,
        llm_id=invocation.llm_id,
        messages=[message.to_payload() for message in invocation.messages],
        input_items=[item.to_payload() for item in invocation.input_items],
        provider_context_messages=[
            message.to_payload() for message in invocation.provider_context_messages
        ],
        tool_schemas=[
            tool_schema.to_payload() for tool_schema in invocation.tool_schemas
        ],
        response_format=(
            dict(invocation.response_format)
            if invocation.response_format is not None
            else None
        ),
        request_policy=dict(invocation.request_policy),
        request_overrides=dict(invocation.request_overrides),
        request_metadata=dict(invocation.request_metadata),
        run_id=invocation.run_id,
        agent_id=invocation.agent_id,
        session_key=invocation.session_key,
        active_session_id=invocation.active_session_id,
        provider_request_payload_preview=dict(
            invocation.provider_request_payload_preview,
        ),
        status=invocation.status.value,
        result_payload=(
            invocation.result.to_payload() if invocation.result is not None else None
        ),
        continuation_payload=(
            invocation.continuation.to_payload()
            if invocation.continuation is not None
            else None
        ),
        error_payload=(
            invocation.error.to_payload() if invocation.error is not None else None
        ),
        provider_request_id=invocation.provider_request_id,
        created_at=invocation.created_at,
        started_at=invocation.started_at,
        completed_at=invocation.completed_at,
        response_items=[
            response_item_to_model(item) for item in invocation.response_items
        ],
    )


def invocation_from_model(model: LlmInvocationModel) -> LlmInvocation:
    return LlmInvocation(
        id=model.id,
        llm_id=model.llm_id,
        messages=tuple(LlmMessage.from_payload(item) for item in model.messages or []),
        input_items=tuple(
            LlmInputItem.from_payload(item) for item in model.input_items or []
        ),
        provider_context_messages=tuple(
            LlmMessage.from_payload(item)
            for item in model.provider_context_messages or []
        ),
        tool_schemas=tuple(
            ToolSchema.from_payload(item) for item in model.tool_schemas or []
        ),
        response_format=(
            dict(model.response_format)
            if isinstance(model.response_format, dict)
            else None
        ),
        request_overrides=(
            dict(model.request_overrides)
            if isinstance(model.request_overrides, dict)
            else {}
        ),
        request_policy=(
            dict(model.request_policy) if isinstance(model.request_policy, dict) else {}
        ),
        request_metadata=(
            dict(model.request_metadata)
            if isinstance(model.request_metadata, dict)
            else {}
        ),
        run_id=model.run_id,
        agent_id=model.agent_id,
        session_key=model.session_key,
        active_session_id=model.active_session_id,
        provider_request_payload_preview=(
            dict(model.provider_request_payload_preview)
            if isinstance(model.provider_request_payload_preview, dict)
            else {}
        ),
        status=LlmInvocationStatus(model.status),
        result=LlmResult.from_payload(model.result_payload),
        response_items=tuple(
            response_item_from_model(item)
            for item in sorted(
                model.response_items or [],
                key=lambda item: item.sequence_no,
            )
        ),
        continuation=LlmContinuationSignal.from_payload(model.continuation_payload),
        error=LlmErrorPayload.from_payload(model.error_payload),
        provider_request_id=model.provider_request_id,
        created_at=coerce_utc_datetime(model.created_at),
        started_at=coerce_optional_utc_datetime(model.started_at),
        completed_at=coerce_optional_utc_datetime(model.completed_at),
    )


def response_item_to_model(item: LlmResponseItem) -> LlmInvocationResponseItemModel:
    return LlmInvocationResponseItemModel(
        id=item.id,
        invocation_id=item.invocation_id,
        sequence_no=item.sequence_no,
        kind=item.kind.value,
        role=item.role.value if item.role is not None else None,
        phase=item.phase.value,
        content_payload=dict(item.content_payload),
        provider_payload=dict(item.provider_payload),
        provider_item_id=item.provider_item_id,
        provider_item_type=item.provider_item_type,
        call_id=item.call_id,
        tool_name=item.tool_name,
        provider_replay_candidate=item.provider_replay_candidate,
        user_timeline_candidate=item.user_timeline_candidate,
        created_at=item.created_at,
        completed_at=item.completed_at,
    )


def response_item_from_model(
    model: LlmInvocationResponseItemModel,
) -> LlmResponseItem:
    return LlmResponseItem(
        id=model.id,
        invocation_id=model.invocation_id,
        sequence_no=model.sequence_no,
        kind=LlmResponseItemKind(model.kind),
        role=LlmMessageRole(model.role) if model.role is not None else None,
        phase=LlmMessagePhase(model.phase),
        content_payload=(
            dict(model.content_payload) if isinstance(model.content_payload, dict) else {}
        ),
        provider_payload=(
            dict(model.provider_payload)
            if isinstance(model.provider_payload, dict)
            else {}
        ),
        provider_item_id=model.provider_item_id,
        provider_item_type=model.provider_item_type,
        call_id=model.call_id,
        tool_name=model.tool_name,
        provider_replay_candidate=model.provider_replay_candidate,
        user_timeline_candidate=model.user_timeline_candidate,
        created_at=coerce_utc_datetime(model.created_at),
        completed_at=coerce_optional_utc_datetime(model.completed_at),
    )


def response_event_to_model(event: LlmResponseEvent) -> LlmInvocationResponseEventModel:
    return LlmInvocationResponseEventModel(
        id=event.id,
        invocation_id=event.invocation_id,
        sequence_no=event.sequence_no,
        type=event.type.value,
        item_id=event.item_id,
        delta_payload=dict(event.delta_payload),
        provider_payload=dict(event.provider_payload),
        created_at=event.created_at,
    )


def response_event_from_model(
    model: LlmInvocationResponseEventModel,
) -> LlmResponseEvent:
    return LlmResponseEvent(
        id=model.id,
        invocation_id=model.invocation_id,
        sequence_no=model.sequence_no,
        type=LlmResponseEventType(model.type),
        item_id=model.item_id,
        delta_payload=(
            dict(model.delta_payload) if isinstance(model.delta_payload, dict) else {}
        ),
        provider_payload=(
            dict(model.provider_payload)
            if isinstance(model.provider_payload, dict)
            else {}
        ),
        created_at=coerce_utc_datetime(model.created_at),
    )


__all__ = [
    "invocation_from_model",
    "invocation_to_model",
    "profile_from_model",
    "profile_to_model",
    "response_event_from_model",
    "response_event_to_model",
    "response_item_from_model",
    "response_item_to_model",
]
