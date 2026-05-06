from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from crxzipple.modules.channels.domain.value_objects import (
    ChannelCapabilities,
    _parse_datetime,
    _utcnow,
)


@dataclass(frozen=True, slots=True)
class ChannelRuntimeRegistration:
    runtime_id: str
    channel_type: str
    service_key: str | None = None
    status: str = "online"
    capabilities: ChannelCapabilities = field(default_factory=ChannelCapabilities)
    metadata: dict[str, Any] = field(default_factory=dict)
    registered_at: datetime = field(default_factory=_utcnow)
    last_heartbeat_at: datetime = field(default_factory=_utcnow)

    def to_payload(self) -> dict[str, Any]:
        return {
            "runtime_id": self.runtime_id,
            "channel_type": self.channel_type,
            "service_key": self.service_key,
            "status": self.status,
            "capabilities": self.capabilities.to_payload(),
            "metadata": dict(self.metadata),
            "registered_at": self.registered_at.isoformat(),
            "last_heartbeat_at": self.last_heartbeat_at.isoformat(),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ChannelRuntimeRegistration":
        return cls(
            runtime_id=str(payload.get("runtime_id") or ""),
            channel_type=str(payload.get("channel_type") or ""),
            service_key=(
                payload.get("service_key")
                if isinstance(payload.get("service_key"), str)
                else None
            ),
            status=str(payload.get("status") or "online"),
            capabilities=ChannelCapabilities.from_payload(
                dict(payload.get("capabilities") or {}),
            ),
            metadata=dict(payload.get("metadata") or {}),
            registered_at=_parse_datetime(payload.get("registered_at")),
            last_heartbeat_at=_parse_datetime(payload.get("last_heartbeat_at")),
        )


@dataclass(frozen=True, slots=True)
class ChannelAccountRuntimeBinding:
    channel_type: str
    channel_account_id: str
    runtime_id: str
    updated_at: datetime = field(default_factory=_utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "channel_type": self.channel_type,
            "channel_account_id": self.channel_account_id,
            "runtime_id": self.runtime_id,
            "updated_at": self.updated_at.isoformat(),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ChannelAccountRuntimeBinding":
        return cls(
            channel_type=str(payload.get("channel_type") or ""),
            channel_account_id=str(payload.get("channel_account_id") or ""),
            runtime_id=str(payload.get("runtime_id") or ""),
            updated_at=_parse_datetime(payload.get("updated_at")),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(frozen=True, slots=True)
class ChannelConnectionBinding:
    channel_type: str
    connection_id: str
    runtime_id: str
    channel_account_id: str | None = None
    conversation_id: str | None = None
    supports_streaming: bool = False
    updated_at: datetime = field(default_factory=_utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "channel_type": self.channel_type,
            "connection_id": self.connection_id,
            "runtime_id": self.runtime_id,
            "channel_account_id": self.channel_account_id,
            "conversation_id": self.conversation_id,
            "supports_streaming": self.supports_streaming,
            "updated_at": self.updated_at.isoformat(),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ChannelConnectionBinding":
        return cls(
            channel_type=str(payload.get("channel_type") or ""),
            connection_id=str(payload.get("connection_id") or ""),
            runtime_id=str(payload.get("runtime_id") or ""),
            channel_account_id=(
                payload.get("channel_account_id")
                if isinstance(payload.get("channel_account_id"), str)
                else None
            ),
            conversation_id=(
                payload.get("conversation_id")
                if isinstance(payload.get("conversation_id"), str)
                else None
            ),
            supports_streaming=bool(payload.get("supports_streaming", False)),
            updated_at=_parse_datetime(payload.get("updated_at")),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(frozen=True, slots=True)
class ChannelInteraction:
    interaction_id: str
    channel_type: str
    channel_account_id: str | None = None
    external_event_id: str | None = None
    external_message_id: str | None = None
    external_conversation_id: str | None = None
    external_user_id: str | None = None
    reply_address: dict[str, Any] = field(default_factory=dict)
    agent_id: str | None = None
    session_key: str | None = None
    run_id: str | None = None
    status: str = "received"
    last_error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def to_payload(self) -> dict[str, Any]:
        return {
            "interaction_id": self.interaction_id,
            "channel_type": self.channel_type,
            "channel_account_id": self.channel_account_id,
            "external_event_id": self.external_event_id,
            "external_message_id": self.external_message_id,
            "external_conversation_id": self.external_conversation_id,
            "external_user_id": self.external_user_id,
            "reply_address": dict(self.reply_address),
            "agent_id": self.agent_id,
            "session_key": self.session_key,
            "run_id": self.run_id,
            "status": self.status,
            "last_error": self.last_error,
            "metadata": dict(self.metadata),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ChannelInteraction":
        return cls(
            interaction_id=str(payload.get("interaction_id") or ""),
            channel_type=str(payload.get("channel_type") or ""),
            channel_account_id=(
                payload.get("channel_account_id")
                if isinstance(payload.get("channel_account_id"), str)
                else None
            ),
            external_event_id=(
                payload.get("external_event_id")
                if isinstance(payload.get("external_event_id"), str)
                else None
            ),
            external_message_id=(
                payload.get("external_message_id")
                if isinstance(payload.get("external_message_id"), str)
                else None
            ),
            external_conversation_id=(
                payload.get("external_conversation_id")
                if isinstance(payload.get("external_conversation_id"), str)
                else None
            ),
            external_user_id=(
                payload.get("external_user_id")
                if isinstance(payload.get("external_user_id"), str)
                else None
            ),
            reply_address=dict(payload.get("reply_address") or {}),
            agent_id=payload.get("agent_id") if isinstance(payload.get("agent_id"), str) else None,
            session_key=(
                payload.get("session_key")
                if isinstance(payload.get("session_key"), str)
                else None
            ),
            run_id=payload.get("run_id") if isinstance(payload.get("run_id"), str) else None,
            status=str(payload.get("status") or "received"),
            last_error=(
                payload.get("last_error")
                if isinstance(payload.get("last_error"), str)
                else None
            ),
            metadata=dict(payload.get("metadata") or {}),
            created_at=_parse_datetime(payload.get("created_at")),
            updated_at=_parse_datetime(payload.get("updated_at")),
        )
