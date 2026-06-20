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


class SessionItemKind(StrEnum):
    USER_MESSAGE = "user_message"
    AGENT_PROGRESS = "agent_progress"
    ASSISTANT_MESSAGE = "assistant_message"
    REASONING = "reasoning"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    PROVIDER_EXTERNAL_ACTIVITY = "provider_external_activity"
    CONTEXT_COMPACTION = "context_compaction"
    RUNTIME_NOTICE = "runtime_notice"
    RUNTIME_ERROR = "runtime_error"
    UNKNOWN = "unknown"


class SessionItemPhase(StrEnum):
    COMMENTARY = "commentary"
    FINAL_ANSWER = "final_answer"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SessionItem(ValueObject):
    id: str
    session_key: str
    session_id: str
    sequence_no: int
    kind: SessionItemKind
    content_payload: dict[str, Any] = field(default_factory=dict)
    role: str | None = None
    phase: SessionItemPhase = SessionItemPhase.UNKNOWN
    source_module: str | None = None
    source_kind: str | None = None
    source_id: str | None = None
    provider_item_id: str | None = None
    provider_item_type: str | None = None
    call_id: str | None = None
    tool_name: str | None = None
    model_visible: bool = True
    user_visible: bool = True
    chat_visible: bool = True
    trace_visible: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise SessionValidationError("Session item id cannot be empty.")
        if not self.session_key.strip():
            raise SessionValidationError("Session item session_key cannot be empty.")
        if not self.session_id.strip():
            raise SessionValidationError("Session item session_id cannot be empty.")
        if self.sequence_no <= 0:
            raise SessionValidationError(
                "Session item sequence_no must be greater than zero.",
            )
        object.__setattr__(self, "content_payload", dict(self.content_payload))
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "session_key": self.session_key,
            "session_id": self.session_id,
            "sequence_no": self.sequence_no,
            "kind": self.kind.value,
            "phase": self.phase.value,
            "content_payload": dict(self.content_payload),
            "model_visible": self.model_visible,
            "user_visible": self.user_visible,
            "chat_visible": self.chat_visible,
            "trace_visible": self.trace_visible,
            "metadata": dict(self.metadata),
            "created_at": self.created_at.isoformat(),
        }
        if self.role is not None:
            payload["role"] = self.role
        if self.source_module is not None:
            payload["source_module"] = self.source_module
        if self.source_kind is not None:
            payload["source_kind"] = self.source_kind
        if self.source_id is not None:
            payload["source_id"] = self.source_id
        if self.provider_item_id is not None:
            payload["provider_item_id"] = self.provider_item_id
        if self.provider_item_type is not None:
            payload["provider_item_type"] = self.provider_item_type
        if self.call_id is not None:
            payload["call_id"] = self.call_id
        if self.tool_name is not None:
            payload["tool_name"] = self.tool_name
        return payload


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
class SessionReply(ValueObject):
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
    def from_payload(cls, payload: dict[str, Any] | None) -> "SessionReply":
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
class SessionRouteContext(ValueObject):
    agent_id: str
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
    workspace: str | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        if self.agent_id is not None:
            payload["agent_id"] = self.agent_id
        if self.workspace is not None:
            payload["workspace"] = self.workspace
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
        workspace = payload.get("workspace")
        return cls(
            agent_id=str(agent_id).strip() or None if agent_id is not None else None,
            workspace=str(workspace).strip() or None if workspace is not None else None,
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
