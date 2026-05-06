from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def channel_broadcast_topic(
    channel_type: str,
    *,
    channel_account_id: str | None = None,
) -> str:
    normalized_channel = channel_type.strip().lower()
    if not normalized_channel:
        raise ValueError("channel_type is required to build a broadcast topic.")
    normalized_account = (
        channel_account_id.strip()
        if isinstance(channel_account_id, str) and channel_account_id.strip()
        else None
    )
    if normalized_account is not None:
        return f"channel.broadcast.{normalized_channel}.account.{normalized_account}"
    return f"channel.broadcast.{normalized_channel}"

def channel_dead_letter_topic(
    channel_type: str,
    *,
    runtime_id: str | None = None,
) -> str:
    normalized_channel = channel_type.strip().lower()
    if not normalized_channel:
        raise ValueError("channel_type is required to build a dead-letter topic.")
    normalized_runtime = (
        runtime_id.strip()
        if isinstance(runtime_id, str) and runtime_id.strip()
        else None
    )
    if normalized_runtime is not None:
        return f"channel.dead_letter.{normalized_channel}.runtime.{normalized_runtime}"
    return f"channel.dead_letter.{normalized_channel}"


def channel_connection_control_topic(
    channel_type: str,
    *,
    connection_id: str,
) -> str:
    normalized_channel = channel_type.strip().lower()
    if not normalized_channel:
        raise ValueError("channel_type is required to build a connection control topic.")
    normalized_connection = (
        connection_id.strip()
        if isinstance(connection_id, str) and connection_id.strip()
        else None
    )
    if normalized_connection is None:
        raise ValueError("connection_id is required to build a connection control topic.")
    return (
        f"channel.connection.{normalized_channel}.connection."
        f"{normalized_connection}.control"
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: object) -> datetime:
    if isinstance(value, str) and value.strip():
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    return _utcnow()


@dataclass(frozen=True, slots=True)
class ChannelCapabilities:
    supports_streaming: bool = False
    supports_binary: bool = False
    supports_threading: bool = False
    supports_edit: bool = False
    supports_ack: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "supports_streaming": self.supports_streaming,
            "supports_binary": self.supports_binary,
            "supports_threading": self.supports_threading,
            "supports_edit": self.supports_edit,
            "supports_ack": self.supports_ack,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ChannelCapabilities":
        return cls(
            supports_streaming=bool(payload.get("supports_streaming", False)),
            supports_binary=bool(payload.get("supports_binary", False)),
            supports_threading=bool(payload.get("supports_threading", False)),
            supports_edit=bool(payload.get("supports_edit", False)),
            supports_ack=bool(payload.get("supports_ack", False)),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(frozen=True, slots=True)
class ChannelAccountProfile:
    account_id: str
    enabled: bool = True
    transport_mode: str = "push"
    auth_ref: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "enabled": self.enabled,
            "transport_mode": self.transport_mode,
            "auth_ref": self.auth_ref,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ChannelAccountProfile":
        return cls(
            account_id=str(payload.get("account_id") or ""),
            enabled=bool(payload.get("enabled", True)),
            transport_mode=str(payload.get("transport_mode") or "push"),
            auth_ref=payload.get("auth_ref") if isinstance(payload.get("auth_ref"), str) else None,
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(frozen=True, slots=True)
class ChannelProfile:
    channel_type: str
    enabled: bool = True
    capabilities: ChannelCapabilities = field(default_factory=ChannelCapabilities)
    accounts: tuple[ChannelAccountProfile, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "channel_type": self.channel_type,
            "enabled": self.enabled,
            "capabilities": self.capabilities.to_payload(),
            "accounts": [account.to_payload() for account in self.accounts],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ChannelProfile":
        raw_accounts = payload.get("accounts")
        account_payloads = raw_accounts if isinstance(raw_accounts, list) else []
        return cls(
            channel_type=str(payload.get("channel_type") or ""),
            enabled=bool(payload.get("enabled", True)),
            capabilities=ChannelCapabilities.from_payload(
                dict(payload.get("capabilities") or {}),
            ),
            accounts=tuple(
                ChannelAccountProfile.from_payload(item)
                for item in account_payloads
                if isinstance(item, dict)
            ),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(frozen=True, slots=True)
class ChannelSystemConfig:
    profiles: tuple[ChannelProfile, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "profiles": [profile.to_payload() for profile in self.profiles],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ChannelSystemConfig":
        raw_profiles = payload.get("profiles")
        profile_payloads = raw_profiles if isinstance(raw_profiles, list) else []
        return cls(
            profiles=tuple(
                ChannelProfile.from_payload(item)
                for item in profile_payloads
                if isinstance(item, dict)
            ),
            metadata=dict(payload.get("metadata") or {}),
        )
