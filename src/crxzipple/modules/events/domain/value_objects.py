from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal, TypeAlias

from crxzipple.shared.domain.events import Event

EventKind: TypeAlias = Literal[
    "command",
    "fact",
    "broadcast",
    "observe",
    "live",
]
EventCursor: TypeAlias = str


class EventOutboxStatus(StrEnum):
    PENDING = "pending"
    PUBLISHING = "publishing"
    DELIVERED = "delivered"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class EventSelector:
    topic: str

    def __post_init__(self) -> None:
        normalized_topic = (
            self.topic.strip()
            if isinstance(self.topic, str) and self.topic.strip()
            else None
        )
        if normalized_topic is None:
            raise ValueError("EventSelector requires a topic.")
        object.__setattr__(self, "topic", normalized_topic)

    @classmethod
    def topic_only(cls, topic: str) -> "EventSelector":
        return cls(topic=topic)

    @property
    def key(self) -> str:
        return f"topic:{self.topic}"


@dataclass(frozen=True, slots=True, init=False)
class EventAddress:
    address: str | None = None
    address_kind: str | None = None
    labels: dict[str, str] = field(default_factory=dict)
    scope: str | None = None
    tenant_id: str | None = None
    route_hint: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        address: str | None = None,
        address_kind: str | None = None,
        labels: dict[str, str] | None = None,
        runtime: str | None = None,
        transport: str | None = None,
        account: str | None = None,
        conversation: str | None = None,
        connection: str | None = None,
        scope: str | None = None,
        tenant_id: str | None = None,
        route_hint: str | None = None,
        metadata: dict[str, Any] | None = None,
        *,
        runtime_id: str | None = None,
        channel_type: str | None = None,
        channel_account_id: str | None = None,
        conversation_id: str | None = None,
        connection_id: str | None = None,
    ) -> None:
        resolved_labels = self._normalize_labels(labels)
        self._set_optional_label(
            resolved_labels,
            "runtime",
            runtime if runtime is not None else runtime_id,
        )
        self._set_optional_label(
            resolved_labels,
            "transport",
            transport if transport is not None else channel_type,
        )
        self._set_optional_label(
            resolved_labels,
            "account",
            account if account is not None else channel_account_id,
        )
        self._set_optional_label(
            resolved_labels,
            "conversation",
            conversation if conversation is not None else conversation_id,
        )
        self._set_optional_label(
            resolved_labels,
            "connection",
            connection if connection is not None else connection_id,
        )
        object.__setattr__(self, "address", self._optional_text(address))
        object.__setattr__(self, "address_kind", self._optional_text(address_kind))
        object.__setattr__(self, "labels", resolved_labels)
        object.__setattr__(self, "scope", scope)
        object.__setattr__(self, "tenant_id", tenant_id)
        object.__setattr__(self, "route_hint", route_hint)
        object.__setattr__(self, "metadata", dict(metadata or {}))

    @property
    def runtime(self) -> str | None:
        return self.labels.get("runtime")

    @property
    def transport(self) -> str | None:
        return self.labels.get("transport")

    @property
    def account(self) -> str | None:
        return self.labels.get("account")

    @property
    def conversation(self) -> str | None:
        return self.labels.get("conversation")

    @property
    def connection(self) -> str | None:
        return self.labels.get("connection")

    @property
    def runtime_id(self) -> str | None:
        return self.runtime

    @property
    def channel_type(self) -> str | None:
        return self.transport

    @property
    def channel_account_id(self) -> str | None:
        return self.account

    @property
    def conversation_id(self) -> str | None:
        return self.conversation

    @property
    def connection_id(self) -> str | None:
        return self.connection

    def to_payload(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "address_kind": self.address_kind,
            "labels": dict(self.labels),
            "runtime": self.runtime,
            "transport": self.transport,
            "account": self.account,
            "conversation": self.conversation,
            "connection": self.connection,
            "scope": self.scope,
            "tenant_id": self.tenant_id,
            "route_hint": self.route_hint,
            "metadata": dict(self.metadata),
            "runtime_id": self.runtime,
            "channel_type": self.transport,
            "channel_account_id": self.account,
            "conversation_id": self.conversation,
            "connection_id": self.connection,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "EventAddress":
        return cls(
            address=cls._optional_text(payload.get("address")),
            address_kind=cls._optional_text(payload.get("address_kind")),
            labels=(
                {
                    str(key): value
                    for key, value in dict(payload.get("labels") or {}).items()
                    if isinstance(value, str)
                }
                if isinstance(payload.get("labels"), dict)
                else None
            ),
            runtime=cls._optional_text(payload.get("runtime"))
            or cls._optional_text(payload.get("runtime_id")),
            transport=cls._optional_text(payload.get("transport"))
            or cls._optional_text(payload.get("channel_type")),
            account=cls._optional_text(payload.get("account"))
            or cls._optional_text(payload.get("channel_account_id")),
            conversation=cls._optional_text(payload.get("conversation"))
            or cls._optional_text(payload.get("conversation_id")),
            connection=cls._optional_text(payload.get("connection"))
            or cls._optional_text(payload.get("connection_id")),
            scope=payload.get("scope") if isinstance(payload.get("scope"), str) else None,
            tenant_id=payload.get("tenant_id") if isinstance(payload.get("tenant_id"), str) else None,
            route_hint=payload.get("route_hint") if isinstance(payload.get("route_hint"), str) else None,
            metadata=dict(payload.get("metadata") or {}),
        )

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        return value if isinstance(value, str) else None

    @classmethod
    def _normalize_labels(cls, labels: dict[str, str] | None) -> dict[str, str]:
        if labels is None:
            return {}
        return {
            str(key): value
            for key, value in labels.items()
            if isinstance(key, str) and key.strip() and isinstance(value, str)
        }

    @classmethod
    def _set_optional_label(
        cls,
        labels: dict[str, str],
        key: str,
        value: str | None,
    ) -> None:
        text = cls._optional_text(value)
        if text is not None:
            labels[key] = text


EventTarget = EventAddress


@dataclass(frozen=True, slots=True)
class EventTopicRecord:
    cursor: EventCursor
    envelope: Event


@dataclass(frozen=True, slots=True)
class EventTopicWatch:
    topic: str
    after_cursor: EventCursor | None = None


@dataclass(frozen=True, slots=True)
class EventSubscriptionCursor:
    subscription_id: str
    source_topic: str
    cursor: EventCursor
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_payload(self) -> dict[str, Any]:
        return {
            "subscription_id": self.subscription_id,
            "source_topic": self.source_topic,
            "cursor": self.cursor,
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "EventSubscriptionCursor | None":
        subscription_id = payload.get("subscription_id")
        source_topic = payload.get("source_topic")
        cursor = payload.get("cursor")
        if not (
            isinstance(subscription_id, str)
            and subscription_id.strip()
            and isinstance(source_topic, str)
            and source_topic.strip()
            and isinstance(cursor, str)
            and cursor.strip()
        ):
            return None
        raw_updated_at = payload.get("updated_at")
        updated_at = (
            datetime.fromisoformat(raw_updated_at)
            if isinstance(raw_updated_at, str) and raw_updated_at.strip()
            else datetime.now(timezone.utc)
        )
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        return cls(
            subscription_id=subscription_id.strip(),
            source_topic=source_topic.strip(),
            cursor=cursor.strip(),
            updated_at=updated_at,
        )
