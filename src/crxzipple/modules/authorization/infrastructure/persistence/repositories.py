from __future__ import annotations

from sqlalchemy import select

from crxzipple.core.db import SessionFactory
from crxzipple.modules.authorization.domain import (
    AuthorizationGrantScope,
    TemporaryAuthorizationGrant,
)
from crxzipple.modules.authorization.infrastructure.persistence.models import (
    TemporaryAuthorizationGrantModel,
)


class SqlAlchemyTemporaryAuthorizationGrantRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def add(self, grant: TemporaryAuthorizationGrant) -> None:
        with self.session_factory() as session:
            session.merge(
                TemporaryAuthorizationGrantModel(
                    id=grant.id,
                    scope=grant.scope.value,
                    run_id=grant.run_id,
                    session_key=grant.session_key,
                    agent_id=grant.agent_id,
                    approval_request_id=grant.approval_request_id,
                    effect_ids_payload=list(grant.effect_ids),
                    tool_ids_payload=list(grant.tool_ids),
                    created_at=grant.created_at,
                ),
            )
            session.commit()

    def list_for_run(self, run_id: str) -> list[TemporaryAuthorizationGrant]:
        with self.session_factory() as session:
            models = session.scalars(
                select(TemporaryAuthorizationGrantModel)
                .where(TemporaryAuthorizationGrantModel.run_id == run_id)
                .order_by(TemporaryAuthorizationGrantModel.created_at.asc()),
            ).all()
        return [self._to_entity(model) for model in models]

    def list_for_session(self, session_key: str) -> list[TemporaryAuthorizationGrant]:
        with self.session_factory() as session:
            models = session.scalars(
                select(TemporaryAuthorizationGrantModel)
                .where(TemporaryAuthorizationGrantModel.session_key == session_key)
                .order_by(TemporaryAuthorizationGrantModel.created_at.asc()),
            ).all()
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_entity(model: TemporaryAuthorizationGrantModel) -> TemporaryAuthorizationGrant:
        return TemporaryAuthorizationGrant(
            id=model.id,
            scope=AuthorizationGrantScope(model.scope),
            run_id=model.run_id,
            session_key=model.session_key,
            agent_id=model.agent_id,
            approval_request_id=model.approval_request_id,
            effect_ids=tuple(model.effect_ids_payload),
            tool_ids=tuple(model.tool_ids_payload),
            created_at=model.created_at,
        )
