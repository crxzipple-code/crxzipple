from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from crxzipple.modules.llm.domain.entities import LlmInvocation, LlmProfile
from crxzipple.modules.llm.domain.value_objects import (
    LlmApiFamily,
    LlmCapability,
    LlmDefaults,
    LlmErrorPayload,
    LlmInvocationStatus,
    LlmMessage,
    LlmModelFamily,
    LlmProviderKind,
    LlmResult,
    LlmSourceKind,
    ToolSchema,
)
from crxzipple.modules.llm.infrastructure.persistence.models import (
    LlmInvocationModel,
    LlmProfileModel,
)


class SqlAlchemyLlmProfileRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, profile: LlmProfile) -> None:
        self.session.merge(
            LlmProfileModel(
                id=profile.id,
                provider=profile.provider.value,
                api_family=profile.api_family.value,
                model_name=profile.model_name,
                context_window_tokens=profile.context_window_tokens,
                model_family=profile.model_family.value,
                capabilities=[item.value for item in profile.capabilities],
                default_params=profile.default_params.to_payload(),
                base_url=profile.base_url,
                credential_binding=profile.credential_binding,
                timeout_seconds=profile.timeout_seconds,
                source_kind=profile.source_kind.value,
                enabled=profile.enabled,
            ),
        )

    def get(self, llm_id: str) -> LlmProfile | None:
        model = self.session.get(LlmProfileModel, llm_id)
        if model is None:
            return None
        return self._to_entity(model)

    def list(self) -> list[LlmProfile]:
        models = self.session.scalars(
            select(LlmProfileModel).order_by(LlmProfileModel.id),
        ).all()
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_entity(model: LlmProfileModel) -> LlmProfile:
        return LlmProfile(
            id=model.id,
            provider=LlmProviderKind(model.provider),
            api_family=LlmApiFamily(model.api_family),
            model_name=model.model_name,
            context_window_tokens=model.context_window_tokens,
            model_family=LlmModelFamily(model.model_family),
            capabilities=tuple(
                LlmCapability(item) for item in (model.capabilities or [])
            ),
            default_params=LlmDefaults.from_payload(model.default_params),
            base_url=model.base_url,
            credential_binding=model.credential_binding,
            timeout_seconds=model.timeout_seconds,
            source_kind=LlmSourceKind(model.source_kind),
            enabled=model.enabled,
        )


class SqlAlchemyLlmInvocationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, invocation: LlmInvocation) -> None:
        self.session.merge(
            LlmInvocationModel(
                id=invocation.id,
                llm_id=invocation.llm_id,
                messages=[message.to_payload() for message in invocation.messages],
                tool_schemas=[
                    tool_schema.to_payload() for tool_schema in invocation.tool_schemas
                ],
                response_format=(
                    dict(invocation.response_format)
                    if invocation.response_format is not None
                    else None
                ),
                request_overrides=dict(invocation.request_overrides),
                status=invocation.status.value,
                result_payload=(
                    invocation.result.to_payload()
                    if invocation.result is not None
                    else None
                ),
                error_payload=(
                    invocation.error.to_payload()
                    if invocation.error is not None
                    else None
                ),
                provider_request_id=invocation.provider_request_id,
                created_at=invocation.created_at,
                started_at=invocation.started_at,
                completed_at=invocation.completed_at,
            ),
        )

    def get(self, invocation_id: str) -> LlmInvocation | None:
        model = self.session.get(LlmInvocationModel, invocation_id)
        if model is None:
            return None
        return self._to_entity(model)

    def list(self, *, llm_id: str | None = None) -> list[LlmInvocation]:
        statement = select(LlmInvocationModel)
        if llm_id is not None:
            statement = statement.where(LlmInvocationModel.llm_id == llm_id)
        models = self.session.scalars(
            statement.order_by(
                LlmInvocationModel.created_at.desc(),
                LlmInvocationModel.id,
            ),
        ).all()
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_entity(model: LlmInvocationModel) -> LlmInvocation:
        return LlmInvocation(
            id=model.id,
            llm_id=model.llm_id,
            messages=tuple(LlmMessage.from_payload(item) for item in model.messages or []),
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
            status=LlmInvocationStatus(model.status),
            result=LlmResult.from_payload(model.result_payload),
            error=LlmErrorPayload.from_payload(model.error_payload),
            provider_request_id=model.provider_request_id,
            created_at=model.created_at,
            started_at=model.started_at,
            completed_at=model.completed_at,
        )
