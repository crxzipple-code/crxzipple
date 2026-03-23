from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from crxzipple.modules.session.domain.exceptions import SessionValidationError
from crxzipple.shared.domain import ValueObject


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SessionKind(StrEnum):
    MAIN = "main"
    DIRECT = "direct"
    GROUP = "group"
    CHANNEL = "channel"
    THREAD = "thread"


class DirectSessionScope(StrEnum):
    MAIN = "main"
    PER_PEER = "per_peer"
    PER_CHANNEL_PEER = "per_channel_peer"
    PER_ACCOUNT_CHANNEL_PEER = "per_account_channel_peer"


class SessionMessageKind(StrEnum):
    MESSAGE = "message"
    TOOL_RESULT = "tool_result"
    EVENT = "event"


class SessionMessageVisibility(StrEnum):
    DEFAULT = "default"
    INTERNAL = "internal"
    ARCHIVED = "archived"


@dataclass(frozen=True, slots=True)
class SessionOrigin(ValueObject):
    label: str | None = None
    provider: str | None = None
    surface: str | None = None
    chat_type: str | None = None
    from_id: str | None = None
    to_id: str | None = None
    account_id: str | None = None
    thread_id: str | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        if self.label is not None:
            payload["label"] = self.label
        if self.provider is not None:
            payload["provider"] = self.provider
        if self.surface is not None:
            payload["surface"] = self.surface
        if self.chat_type is not None:
            payload["chat_type"] = self.chat_type
        if self.from_id is not None:
            payload["from"] = self.from_id
        if self.to_id is not None:
            payload["to"] = self.to_id
        if self.account_id is not None:
            payload["account_id"] = self.account_id
        if self.thread_id is not None:
            payload["thread_id"] = self.thread_id
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "SessionOrigin":
        payload = payload or {}
        return cls(
            label=str(payload["label"]) if payload.get("label") is not None else None,
            provider=(
                str(payload["provider"]) if payload.get("provider") is not None else None
            ),
            surface=str(payload["surface"]) if payload.get("surface") is not None else None,
            chat_type=(
                str(payload["chat_type"]) if payload.get("chat_type") is not None else None
            ),
            from_id=str(payload["from"]) if payload.get("from") is not None else None,
            to_id=str(payload["to"]) if payload.get("to") is not None else None,
            account_id=(
                str(payload["account_id"])
                if payload.get("account_id") is not None
                else None
            ),
            thread_id=(
                str(payload["thread_id"])
                if payload.get("thread_id") is not None
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class SessionDelivery(ValueObject):
    channel: str | None = None
    to_id: str | None = None
    account_id: str | None = None
    thread_id: str | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        if self.channel is not None:
            payload["channel"] = self.channel
        if self.to_id is not None:
            payload["to"] = self.to_id
        if self.account_id is not None:
            payload["account_id"] = self.account_id
        if self.thread_id is not None:
            payload["thread_id"] = self.thread_id
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "SessionDelivery":
        payload = payload or {}
        return cls(
            channel=str(payload["channel"]) if payload.get("channel") is not None else None,
            to_id=str(payload["to"]) if payload.get("to") is not None else None,
            account_id=(
                str(payload["account_id"])
                if payload.get("account_id") is not None
                else None
            ),
            thread_id=(
                str(payload["thread_id"])
                if payload.get("thread_id") is not None
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class SessionMessage(ValueObject):
    id: str
    session_key: str
    session_id: str
    sequence_no: int
    role: str
    kind: SessionMessageKind = SessionMessageKind.MESSAGE
    content: str | None = None
    content_payload: dict[str, Any] = field(default_factory=dict)
    source_kind: str | None = None
    source_id: str | None = None
    visibility: SessionMessageVisibility = SessionMessageVisibility.DEFAULT
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise SessionValidationError("Session message id cannot be empty.")
        if not self.session_key.strip():
            raise SessionValidationError("Session message session_key cannot be empty.")
        if not self.session_id.strip():
            raise SessionValidationError("Session message session_id cannot be empty.")
        if self.sequence_no <= 0:
            raise SessionValidationError(
                "Session message sequence_no must be greater than zero.",
            )
        if not self.role.strip():
            raise SessionValidationError("Session message role cannot be empty.")
        has_content = self.content is not None and self.content.strip() != ""
        has_payload = bool(self.content_payload)
        if not has_content and not has_payload:
            raise SessionValidationError(
                "Session message content or content_payload is required.",
            )
        object.__setattr__(self, "content_payload", dict(self.content_payload))
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_key": self.session_key,
            "session_id": self.session_id,
            "sequence_no": self.sequence_no,
            "role": self.role,
            "kind": self.kind.value,
            "content": self.content,
            "content_payload": dict(self.content_payload),
            "source_kind": self.source_kind,
            "source_id": self.source_id,
            "visibility": self.visibility.value,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class SessionRouteContext(ValueObject):
    agent_id: str
    llm_id: str
    channel: str | None = None
    chat_type: str = SessionKind.DIRECT.value
    peer_id: str | None = None
    conversation_id: str | None = None
    thread_id: str | None = None
    account_id: str | None = None
    label: str | None = None
    surface: str | None = None
    main_key: str = "main"
    direct_scope: DirectSessionScope = DirectSessionScope.MAIN
    status: str = "active"
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.agent_id.strip():
            raise SessionValidationError("Session route agent_id cannot be empty.")
        if not self.llm_id.strip():
            raise SessionValidationError("Session route llm_id cannot be empty.")
        if not self.main_key.strip():
            raise SessionValidationError("Session route main_key cannot be empty.")
        if not self.status.strip():
            raise SessionValidationError("Session route status cannot be empty.")
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True, slots=True)
class SessionKeyResolution(ValueObject):
    key: str
    kind: SessionKind
    channel: str | None = None
    chat_type: str | None = None


@dataclass(frozen=True, slots=True)
class SessionRuntimeBinding(ValueObject):
    agent_id: str | None = None
    llm_id: str | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        if self.agent_id is not None:
            payload["agent_id"] = self.agent_id
        if self.llm_id is not None:
            payload["llm_id"] = self.llm_id
        return payload

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
    ) -> "SessionRuntimeBinding":
        payload = payload or {}
        nested = payload.get("runtime_binding")
        if isinstance(nested, dict):
            payload = nested
        agent_id = payload.get("agent_id")
        llm_id = payload.get("llm_id")
        return cls(
            agent_id=str(agent_id).strip() or None if agent_id is not None else None,
            llm_id=str(llm_id).strip() or None if llm_id is not None else None,
        )


@dataclass(frozen=True, slots=True)
class SessionResetPolicy(ValueObject):
    idle_minutes: int | None = None
    daily_reset_hour_utc: int | None = None

    def __post_init__(self) -> None:
        if self.idle_minutes is not None and self.idle_minutes <= 0:
            raise SessionValidationError("Session idle_minutes must be greater than zero.")
        if self.daily_reset_hour_utc is not None and not 0 <= self.daily_reset_hour_utc <= 23:
            raise SessionValidationError(
                "Session daily_reset_hour_utc must be between 0 and 23.",
            )


@dataclass(frozen=True, slots=True)
class SessionResetDecision(ValueObject):
    should_reset: bool
    reason: str | None = None
    expires_at: datetime | None = None
