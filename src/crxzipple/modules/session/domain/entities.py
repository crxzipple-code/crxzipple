from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from crxzipple.modules.session.domain.exceptions import SessionValidationError
from crxzipple.modules.session.domain.value_objects import (
    SessionDelivery,
    SessionKind,
    SessionOrigin,
    SessionRuntimeBinding,
    utcnow,
)
from crxzipple.shared.domain import Entity
from crxzipple.shared.domain import AggregateRoot


@dataclass(kw_only=True)
class Session(AggregateRoot[str]):
    agent_id: str | None = None
    llm_id: str | None = None
    active_session_id: str = field(default_factory=lambda: str(uuid4()))
    status: str = "active"
    channel: str | None = None
    chat_type: str | None = None
    origin: SessionOrigin = field(default_factory=SessionOrigin)
    delivery: SessionDelivery = field(default_factory=SessionDelivery)
    metadata: dict[str, object] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    last_reset_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise SessionValidationError("Session key cannot be empty.")
        if not self.active_session_id.strip():
            raise SessionValidationError("Session active_session_id cannot be empty.")
        if not self.status.strip():
            raise SessionValidationError("Session status cannot be empty.")
        self.agent_id = self.agent_id.strip() or None if self.agent_id is not None else None
        self.llm_id = self.llm_id.strip() or None if self.llm_id is not None else None
        self.metadata = dict(self.metadata)
        binding = self.runtime_binding()
        if binding.agent_id is not None or binding.llm_id is not None:
            self.sync_runtime_binding(
                agent_id=binding.agent_id,
                llm_id=binding.llm_id,
            )

    def runtime_binding(self) -> SessionRuntimeBinding:
        binding = SessionRuntimeBinding.from_payload(self.metadata)
        return SessionRuntimeBinding(
            agent_id=binding.agent_id or self.agent_id,
            llm_id=binding.llm_id or self.llm_id,
        )

    def sync_runtime_binding(
        self,
        *,
        agent_id: str | None = None,
        llm_id: str | None = None,
    ) -> None:
        current = self.runtime_binding()
        resolved_agent_id = (
            agent_id.strip() if agent_id is not None else current.agent_id or self.agent_id
        )
        resolved_llm_id = (
            llm_id.strip() if llm_id is not None else current.llm_id or self.llm_id
        )
        if not resolved_agent_id:
            raise SessionValidationError("Session runtime binding agent_id cannot be empty.")
        if not resolved_llm_id:
            raise SessionValidationError("Session runtime binding llm_id cannot be empty.")
        self.agent_id = resolved_agent_id
        self.llm_id = resolved_llm_id
        self.metadata["runtime_binding"] = SessionRuntimeBinding(
            agent_id=resolved_agent_id,
            llm_id=resolved_llm_id,
        ).to_payload()

    def apply_updates(
        self,
        *,
        llm_id: str | None = None,
        status: str | None = None,
        channel: str | None = None,
        chat_type: str | None = None,
        origin: SessionOrigin | None = None,
        delivery: SessionDelivery | None = None,
        metadata: dict[str, object] | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        if llm_id is not None:
            normalized_llm_id = llm_id.strip()
            if not normalized_llm_id:
                raise SessionValidationError("Session llm_id cannot be empty.")
            self.llm_id = normalized_llm_id
        if status is not None:
            if not status.strip():
                raise SessionValidationError("Session status cannot be empty.")
            self.status = status
        if channel is not None:
            self.channel = channel.strip() or None
        if chat_type is not None:
            self.chat_type = chat_type.strip() or None
        if origin is not None:
            self.origin = origin
        if delivery is not None:
            self.delivery = delivery
        if metadata:
            self.metadata.update(metadata)
        self.sync_runtime_binding(agent_id=self.agent_id, llm_id=self.llm_id)
        self.updated_at = updated_at or utcnow()

    def reset(
        self,
        *,
        active_session_id: str | None = None,
        llm_id: str | None = None,
        status: str | None = None,
        metadata: dict[str, object] | None = None,
        happened_at: datetime | None = None,
    ) -> None:
        next_active_session_id = (active_session_id or str(uuid4())).strip()
        if not next_active_session_id:
            raise SessionValidationError("Session active_session_id cannot be empty.")
        if llm_id is not None:
            normalized_llm_id = llm_id.strip()
            if not normalized_llm_id:
                raise SessionValidationError("Session llm_id cannot be empty.")
            self.llm_id = normalized_llm_id
        if status is not None:
            if not status.strip():
                raise SessionValidationError("Session status cannot be empty.")
            self.status = status
        if metadata:
            self.metadata.update(metadata)
        self.sync_runtime_binding(agent_id=self.agent_id, llm_id=self.llm_id)
        timestamp = happened_at or utcnow()
        self.active_session_id = next_active_session_id
        self.updated_at = timestamp
        self.last_reset_at = timestamp


@dataclass(kw_only=True)
class SessionInstance(Entity[str]):
    session_key: str
    sequence_no: int
    kind: SessionKind = SessionKind.MAIN
    status: str = "active"
    opened_at: datetime = field(default_factory=utcnow)
    closed_at: datetime | None = None
    reset_reason: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise SessionValidationError("Session instance id cannot be empty.")
        if not self.session_key.strip():
            raise SessionValidationError("Session instance session_key cannot be empty.")
        if self.sequence_no <= 0:
            raise SessionValidationError(
                "Session instance sequence_no must be greater than zero.",
            )
        if not self.status.strip():
            raise SessionValidationError("Session instance status cannot be empty.")
        self.metadata = dict(self.metadata)

    def close(
        self,
        *,
        reason: str | None = None,
        closed_at: datetime | None = None,
    ) -> None:
        self.status = "closed"
        self.reset_reason = reason
        self.closed_at = closed_at or utcnow()
