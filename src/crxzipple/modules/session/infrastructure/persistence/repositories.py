from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from crxzipple.modules.session.domain.entities import (
    Session as DomainSession,
    SessionInstance as DomainSessionInstance,
)
from crxzipple.modules.session.domain.value_objects import (
    SessionDelivery,
    SessionKind,
    SessionMessage,
    SessionMessageKind,
    SessionMessageVisibility,
    SessionOrigin,
    SessionRuntimeBinding,
)
from crxzipple.modules.session.infrastructure.persistence.models import (
    SessionInstanceModel,
    SessionMessageModel,
    SessionModel,
)


class SqlAlchemySessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, session: DomainSession) -> None:
        binding = session.runtime_binding()
        self.session.merge(
            SessionModel(
                id=session.id,
                active_session_id=session.active_session_id,
                agent_id=binding.agent_id or session.agent_id,
                status=session.status,
                channel=session.channel,
                chat_type=session.chat_type,
                origin_payload=session.origin.to_payload(),
                delivery_payload=session.delivery.to_payload(),
                metadata_payload=dict(session.metadata),
                created_at=session.created_at,
                updated_at=session.updated_at,
                last_reset_at=session.last_reset_at,
            ),
        )

    def get(self, session_key: str) -> DomainSession | None:
        model = self.session.get(SessionModel, session_key)
        if model is None:
            return None
        return self._to_entity(model)

    def list(self, *, agent_id: str | None = None) -> list[DomainSession]:
        statement = select(SessionModel)
        models = self.session.scalars(
            statement.order_by(SessionModel.updated_at.desc(), SessionModel.id),
        ).all()
        items = [self._to_entity(model) for model in models]
        if agent_id is not None:
            normalized_agent_id = agent_id.strip()
            items = [
                item
                for item in items
                if item.runtime_binding().agent_id == normalized_agent_id
            ]
        return items

    @staticmethod
    def _to_entity(model: SessionModel) -> DomainSession:
        metadata = (
            dict(model.metadata_payload)
            if isinstance(model.metadata_payload, dict)
            else {}
        )
        binding = SessionRuntimeBinding.from_payload(metadata)
        return DomainSession(
            id=model.id,
            active_session_id=model.active_session_id,
            agent_id=binding.agent_id or model.agent_id,
            status=model.status,
            channel=model.channel,
            chat_type=model.chat_type,
            origin=SessionOrigin.from_payload(model.origin_payload),
            delivery=SessionDelivery.from_payload(model.delivery_payload),
            metadata=metadata,
            created_at=model.created_at,
            updated_at=model.updated_at,
            last_reset_at=model.last_reset_at,
        )


class SqlAlchemySessionMessageRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, message: SessionMessage) -> None:
        self.session.merge(
            SessionMessageModel(
                id=message.id,
                session_key=message.session_key,
                session_id=message.session_id,
                sequence_no=message.sequence_no,
                role=message.role,
                kind=message.kind.value,
                content_payload=dict(message.content_payload),
                source_kind=message.source_kind,
                source_id=message.source_id,
                visibility=message.visibility.value,
                metadata_payload=dict(message.metadata),
                created_at=message.created_at,
            ),
        )

    def get(self, message_id: str) -> SessionMessage | None:
        model = self.session.get(SessionMessageModel, message_id)
        if model is None:
            return None
        return self._to_entity(model)

    def get_by_source(
        self,
        *,
        session_key: str,
        session_id: str,
        source_kind: str,
        source_id: str,
    ) -> SessionMessage | None:
        model = self.session.scalar(
            select(SessionMessageModel)
            .where(
                SessionMessageModel.session_key == session_key,
                SessionMessageModel.session_id == session_id,
                SessionMessageModel.source_kind == source_kind,
                SessionMessageModel.source_id == source_id,
            )
            .order_by(
                SessionMessageModel.created_at.desc(),
                SessionMessageModel.sequence_no.desc(),
                SessionMessageModel.id.desc(),
            )
            .limit(1),
        )
        if model is None:
            return None
        return self._to_entity(model)

    def max_sequence_no(self, *, session_key: str, session_id: str) -> int:
        value = self.session.scalar(
            select(func.max(SessionMessageModel.sequence_no)).where(
                SessionMessageModel.session_key == session_key,
                SessionMessageModel.session_id == session_id,
            ),
        )
        return int(value or 0)

    def list(
        self,
        *,
        session_key: str,
        session_id: str | None = None,
        limit: int | None = None,
        include_archived: bool = True,
    ) -> list[SessionMessage]:
        statement = select(SessionMessageModel).where(
            SessionMessageModel.session_key == session_key,
        )
        if session_id is not None:
            statement = statement.where(SessionMessageModel.session_id == session_id)
        if not include_archived:
            statement = statement.where(
                SessionMessageModel.visibility != SessionMessageVisibility.ARCHIVED.value,
            )
        statement = statement.order_by(
            SessionMessageModel.created_at.desc(),
            SessionMessageModel.sequence_no.desc(),
            SessionMessageModel.id.desc(),
        )
        if limit is not None and limit > 0:
            statement = statement.limit(limit)
        models = self.session.scalars(statement).all()
        messages = [self._to_entity(model) for model in reversed(models)]
        return messages

    @staticmethod
    def _to_entity(model: SessionMessageModel) -> SessionMessage:
        return SessionMessage(
            id=model.id,
            session_key=model.session_key,
            session_id=model.session_id,
            sequence_no=model.sequence_no,
            role=model.role,
            kind=SessionMessageKind(model.kind),
            content_payload=(
                dict(model.content_payload)
                if isinstance(model.content_payload, dict)
                else {}
            ),
            source_kind=model.source_kind,
            source_id=model.source_id,
            visibility=SessionMessageVisibility(model.visibility),
            metadata=(
                dict(model.metadata_payload)
                if isinstance(model.metadata_payload, dict)
                else {}
            ),
            created_at=model.created_at,
        )


class SqlAlchemySessionInstanceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, instance: DomainSessionInstance) -> None:
        self.session.merge(
            SessionInstanceModel(
                id=instance.id,
                session_key=instance.session_key,
                sequence_no=instance.sequence_no,
                kind=instance.kind.value,
                status=instance.status,
                opened_at=instance.opened_at,
                closed_at=instance.closed_at,
                reset_reason=instance.reset_reason,
                metadata_payload=dict(instance.metadata),
            ),
        )

    def get(self, instance_id: str) -> DomainSessionInstance | None:
        model = self.session.get(SessionInstanceModel, instance_id)
        if model is None:
            return None
        return self._to_entity(model)

    def list(self, *, session_key: str) -> list[DomainSessionInstance]:
        models = self.session.scalars(
            select(SessionInstanceModel)
            .where(SessionInstanceModel.session_key == session_key)
            .order_by(
                SessionInstanceModel.sequence_no,
                SessionInstanceModel.id,
            ),
        ).all()
        return [self._to_entity(model) for model in models]

    def max_sequence_no(self, *, session_key: str) -> int:
        value = self.session.scalar(
            select(func.max(SessionInstanceModel.sequence_no)).where(
                SessionInstanceModel.session_key == session_key,
            ),
        )
        return int(value or 0)

    @staticmethod
    def _to_entity(model: SessionInstanceModel) -> DomainSessionInstance:
        return DomainSessionInstance(
            id=model.id,
            session_key=model.session_key,
            sequence_no=model.sequence_no,
            kind=SessionKind(model.kind),
            status=model.status,
            opened_at=model.opened_at,
            closed_at=model.closed_at,
            reset_reason=model.reset_reason,
            metadata=(
                dict(model.metadata_payload)
                if isinstance(model.metadata_payload, dict)
                else {}
            ),
        )
