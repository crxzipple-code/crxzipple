from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.llm.domain.enums import (
    LlmMessagePhase,
    LlmMessageRole,
    LlmResponseEventType,
    LlmResponseItemKind,
)
from crxzipple.modules.llm.domain.exceptions import LlmValidationError
from crxzipple.shared.domain import ValueObject


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class LlmResponseItem(ValueObject):
    id: str
    invocation_id: str
    sequence_no: int
    kind: LlmResponseItemKind
    role: LlmMessageRole | None = None
    phase: LlmMessagePhase = LlmMessagePhase.UNKNOWN
    content_payload: dict[str, Any] = field(default_factory=dict)
    provider_payload: dict[str, Any] = field(default_factory=dict)
    provider_item_id: str | None = None
    provider_item_type: str | None = None
    call_id: str | None = None
    tool_name: str | None = None
    provider_replay_candidate: bool = True
    user_timeline_candidate: bool = False
    created_at: datetime = field(default_factory=utcnow)
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise LlmValidationError("LLM response item id cannot be empty.")
        if not self.invocation_id.strip():
            raise LlmValidationError("LLM response item invocation_id cannot be empty.")
        if self.sequence_no < 0:
            raise LlmValidationError("LLM response item sequence_no cannot be negative.")
        object.__setattr__(self, "content_payload", dict(self.content_payload))
        object.__setattr__(self, "provider_payload", dict(self.provider_payload))

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "invocation_id": self.invocation_id,
            "sequence_no": self.sequence_no,
            "kind": self.kind.value,
            "phase": self.phase.value,
            "content_payload": dict(self.content_payload),
            "provider_payload": dict(self.provider_payload),
            "provider_replay_candidate": self.provider_replay_candidate,
            "user_timeline_candidate": self.user_timeline_candidate,
            "created_at": self.created_at.isoformat(),
        }
        if self.role is not None:
            payload["role"] = self.role.value
        if self.provider_item_id is not None:
            payload["provider_item_id"] = self.provider_item_id
        if self.provider_item_type is not None:
            payload["provider_item_type"] = self.provider_item_type
        if self.call_id is not None:
            payload["call_id"] = self.call_id
        if self.tool_name is not None:
            payload["tool_name"] = self.tool_name
        if self.completed_at is not None:
            payload["completed_at"] = self.completed_at.isoformat()
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "LlmResponseItem":
        return cls(
            id=str(payload.get("id", "")),
            invocation_id=str(payload.get("invocation_id", "")),
            sequence_no=int(payload.get("sequence_no", 0)),
            kind=LlmResponseItemKind(str(payload.get("kind", LlmResponseItemKind.UNKNOWN))),
            role=(
                LlmMessageRole(str(payload["role"]))
                if payload.get("role") is not None
                else None
            ),
            phase=LlmMessagePhase(str(payload.get("phase", LlmMessagePhase.UNKNOWN))),
            content_payload=(
                dict(payload.get("content_payload"))
                if isinstance(payload.get("content_payload"), dict)
                else {}
            ),
            provider_payload=(
                dict(payload.get("provider_payload"))
                if isinstance(payload.get("provider_payload"), dict)
                else {}
            ),
            provider_item_id=(
                str(payload["provider_item_id"])
                if payload.get("provider_item_id") is not None
                else None
            ),
            provider_item_type=(
                str(payload["provider_item_type"])
                if payload.get("provider_item_type") is not None
                else None
            ),
            call_id=str(payload["call_id"]) if payload.get("call_id") is not None else None,
            tool_name=(
                str(payload["tool_name"]) if payload.get("tool_name") is not None else None
            ),
            provider_replay_candidate=bool(payload.get("provider_replay_candidate", True)),
            user_timeline_candidate=bool(payload.get("user_timeline_candidate", False)),
            created_at=_datetime_from_payload(payload.get("created_at")) or utcnow(),
            completed_at=_datetime_from_payload(payload.get("completed_at")),
        )


@dataclass(frozen=True, slots=True)
class LlmResponseEvent(ValueObject):
    id: str
    invocation_id: str
    sequence_no: int
    type: LlmResponseEventType
    item_id: str | None = None
    delta_payload: dict[str, Any] = field(default_factory=dict)
    provider_payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise LlmValidationError("LLM response event id cannot be empty.")
        if not self.invocation_id.strip():
            raise LlmValidationError("LLM response event invocation_id cannot be empty.")
        if self.sequence_no < 0:
            raise LlmValidationError("LLM response event sequence_no cannot be negative.")
        object.__setattr__(self, "delta_payload", dict(self.delta_payload))
        object.__setattr__(self, "provider_payload", dict(self.provider_payload))

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "invocation_id": self.invocation_id,
            "sequence_no": self.sequence_no,
            "type": self.type.value,
            "delta_payload": dict(self.delta_payload),
            "provider_payload": dict(self.provider_payload),
            "created_at": self.created_at.isoformat(),
        }
        if self.item_id is not None:
            payload["item_id"] = self.item_id
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "LlmResponseEvent":
        return cls(
            id=str(payload.get("id", "")),
            invocation_id=str(payload.get("invocation_id", "")),
            sequence_no=int(payload.get("sequence_no", 0)),
            type=LlmResponseEventType(str(payload.get("type", LlmResponseEventType.FAILED))),
            item_id=str(payload["item_id"]) if payload.get("item_id") is not None else None,
            delta_payload=(
                dict(payload.get("delta_payload"))
                if isinstance(payload.get("delta_payload"), dict)
                else {}
            ),
            provider_payload=(
                dict(payload.get("provider_payload"))
                if isinstance(payload.get("provider_payload"), dict)
                else {}
            ),
            created_at=_datetime_from_payload(payload.get("created_at")) or utcnow(),
        )


@dataclass(frozen=True, slots=True)
class LlmResponseEventRetentionPolicy(ValueObject):
    full_event_window_seconds: int
    detail_event_limit: int
    durable_fact: str
    overflow_action: str

    def __post_init__(self) -> None:
        if self.full_event_window_seconds <= 0:
            raise LlmValidationError(
                "LLM response event retention window must be greater than zero.",
            )
        if self.detail_event_limit <= 0:
            raise LlmValidationError(
                "LLM response event detail limit must be greater than zero.",
            )
        object.__setattr__(self, "durable_fact", str(self.durable_fact).strip())
        object.__setattr__(self, "overflow_action", str(self.overflow_action).strip())
        if not self.durable_fact:
            raise LlmValidationError("LLM response event durable fact cannot be empty.")
        if not self.overflow_action:
            raise LlmValidationError("LLM response event overflow action cannot be empty.")

    def to_payload(self) -> dict[str, Any]:
        return {
            "full_event_window_seconds": self.full_event_window_seconds,
            "detail_event_limit": self.detail_event_limit,
            "durable_fact": self.durable_fact,
            "overflow_action": self.overflow_action,
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
    ) -> "LlmResponseEventRetentionPolicy":
        return cls(
            full_event_window_seconds=int(payload.get("full_event_window_seconds", 0)),
            detail_event_limit=int(payload.get("detail_event_limit", 0)),
            durable_fact=str(payload.get("durable_fact", "")),
            overflow_action=str(payload.get("overflow_action", "")),
        )


def _datetime_from_payload(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str) and value.strip():
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    return None


__all__ = [
    "LlmResponseEvent",
    "LlmResponseEventRetentionPolicy",
    "LlmResponseItem",
    "utcnow",
]
