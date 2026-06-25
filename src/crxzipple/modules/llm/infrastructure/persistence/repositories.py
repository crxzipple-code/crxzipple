from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from crxzipple.modules.llm.domain.entities import LlmInvocation, LlmProfile
from crxzipple.modules.llm.domain import (
    LlmResponseEvent,
    LlmResponseItem,
)
from crxzipple.modules.llm.infrastructure.persistence.repository_mappers import (
    invocation_from_model,
    invocation_to_model,
    profile_from_model,
    profile_to_model,
    response_event_from_model,
    response_event_to_model,
    response_item_from_model,
)
from crxzipple.modules.llm.infrastructure.persistence.models import (
    LlmInvocationModel,
    LlmInvocationResponseEventModel,
    LlmInvocationResponseItemModel,
    LlmProfileModel,
)


class SqlAlchemyLlmProfileRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, profile: LlmProfile) -> None:
        self.session.merge(profile_to_model(profile))

    def delete(self, llm_id: str) -> None:
        model = self.session.get(LlmProfileModel, llm_id)
        if model is not None:
            self.session.delete(model)

    def get(self, llm_id: str) -> LlmProfile | None:
        model = self.session.get(LlmProfileModel, llm_id)
        if model is None:
            return None
        return profile_from_model(model)

    def list(self) -> list[LlmProfile]:
        models = self.session.scalars(
            select(LlmProfileModel).order_by(LlmProfileModel.id),
        ).all()
        return [profile_from_model(model) for model in models]


class SqlAlchemyLlmInvocationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, invocation: LlmInvocation) -> None:
        self.session.merge(invocation_to_model(invocation))

    def get(self, invocation_id: str) -> LlmInvocation | None:
        model = self.session.get(LlmInvocationModel, invocation_id)
        if model is None:
            return None
        return invocation_from_model(model)

    def list(
        self,
        *,
        llm_id: str | None = None,
        run_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[LlmInvocation]:
        statement = select(LlmInvocationModel)
        if llm_id is not None:
            statement = statement.where(LlmInvocationModel.llm_id == llm_id)
        if run_id is not None:
            statement = statement.where(LlmInvocationModel.run_id == run_id)
        statement = statement.order_by(
            LlmInvocationModel.created_at.desc(),
            LlmInvocationModel.id,
        )
        if offset > 0:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(max(int(limit), 0))
        models = self.session.scalars(
            statement,
        ).all()
        return [invocation_from_model(model) for model in models]

    def add_response_event(self, event: LlmResponseEvent) -> None:
        self.session.merge(response_event_to_model(event))

    def list_response_events(
        self,
        invocation_id: str,
        *,
        limit: int | None = None,
        after_sequence: int | None = None,
    ) -> list[LlmResponseEvent]:
        statement = select(LlmInvocationResponseEventModel).where(
            LlmInvocationResponseEventModel.invocation_id == invocation_id,
        )
        if after_sequence is not None:
            statement = statement.where(
                LlmInvocationResponseEventModel.sequence_no > int(after_sequence),
            )
        statement = statement.order_by(
            LlmInvocationResponseEventModel.sequence_no,
            LlmInvocationResponseEventModel.id,
        )
        if limit is not None:
            statement = statement.limit(max(int(limit), 0))
        models = self.session.scalars(statement).all()
        return [response_event_from_model(model) for model in models]

    def get_response_item(self, item_id: str) -> LlmResponseItem | None:
        model = self.session.get(LlmInvocationResponseItemModel, item_id)
        if model is None:
            return None
        return response_item_from_model(model)
