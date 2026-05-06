from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from crxzipple.modules.session.application.services import RoutedSessionResult
from crxzipple.modules.session.domain.entities import Session, SessionInstance
from crxzipple.modules.session.domain.value_objects import (
    SessionMessage,
    SessionRuntimeBinding,
)


@dataclass(frozen=True, slots=True)
class SessionRuntimeBindingDTO:
    agent_id: str | None
    workspace: str | None

    @classmethod
    def from_value_object(
        cls,
        binding: SessionRuntimeBinding,
    ) -> "SessionRuntimeBindingDTO":
        return cls(
            agent_id=binding.agent_id,
            workspace=binding.workspace,
        )

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, object],
    ) -> "SessionRuntimeBindingDTO":
        return cls.from_value_object(SessionRuntimeBinding.from_payload(payload))


@dataclass(frozen=True, slots=True)
class SessionDTO:
    key: str
    runtime_binding: SessionRuntimeBindingDTO
    active_session_id: str
    status: str
    channel: str | None
    chat_type: str | None
    origin: dict[str, object]
    reply: dict[str, object]
    metadata: dict[str, object]
    created_at: datetime
    updated_at: datetime
    last_reset_at: datetime

    @classmethod
    def from_entity(cls, session: Session) -> "SessionDTO":
        binding = session.runtime_binding()
        return cls(
            key=session.id,
            runtime_binding=SessionRuntimeBindingDTO.from_value_object(binding),
            active_session_id=session.active_session_id,
            status=session.status,
            channel=session.channel,
            chat_type=session.chat_type,
            origin=session.origin.to_payload(),
            reply=session.reply.to_payload(),
            metadata=dict(session.metadata),
            created_at=session.created_at,
            updated_at=session.updated_at,
            last_reset_at=session.last_reset_at,
        )


@dataclass(frozen=True, slots=True)
class SessionMessageDTO:
    id: str
    session_key: str
    session_id: str
    sequence_no: int
    role: str
    kind: str
    content_payload: dict[str, object]
    source_kind: str | None
    source_id: str | None
    visibility: str
    metadata: dict[str, object]
    created_at: datetime

    @classmethod
    def from_entity(cls, message: SessionMessage) -> "SessionMessageDTO":
        return cls(
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
            metadata=dict(message.metadata),
            created_at=message.created_at,
        )


@dataclass(frozen=True, slots=True)
class SessionInstanceDTO:
    id: str
    session_key: str
    runtime_binding: SessionRuntimeBindingDTO
    sequence_no: int
    kind: str
    status: str
    opened_at: datetime
    closed_at: datetime | None
    reset_reason: str | None
    metadata: dict[str, object]

    @classmethod
    def from_entity(cls, instance: SessionInstance) -> "SessionInstanceDTO":
        return cls(
            id=instance.id,
            session_key=instance.session_key,
            runtime_binding=SessionRuntimeBindingDTO.from_payload(instance.metadata),
            sequence_no=instance.sequence_no,
            kind=instance.kind.value,
            status=instance.status,
            opened_at=instance.opened_at,
            closed_at=instance.closed_at,
            reset_reason=instance.reset_reason,
            metadata=dict(instance.metadata),
        )


@dataclass(frozen=True, slots=True)
class ResolveSessionDTO:
    key: str
    kind: str
    created: bool
    reset: bool
    reset_reason: str | None
    session: SessionDTO | None
    active_instance: SessionInstanceDTO | None

    @classmethod
    def from_result(cls, result: RoutedSessionResult) -> "ResolveSessionDTO":
        return cls(
            key=result.resolution.key,
            kind=result.resolution.kind.value,
            created=result.resolution.created,
            reset=result.resolution.reset,
            reset_reason=result.resolution.reset_reason,
            session=(
                SessionDTO.from_entity(result.session)
                if result.session is not None
                else None
            ),
            active_instance=(
                SessionInstanceDTO.from_entity(result.active_instance)
                if result.active_instance is not None
                else None
            ),
        )
