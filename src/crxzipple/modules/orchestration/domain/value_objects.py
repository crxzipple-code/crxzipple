from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationValidationError,
)
from crxzipple.shared.domain import ValueObject


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OrchestrationRunStatus(StrEnum):
    ACCEPTED = "accepted"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OrchestrationRunStage(StrEnum):
    ACCEPTED = "accepted"
    ROUTED = "routed"
    BULK_READY = "bulk_ready"
    QUEUED = "queued"
    RUNNING = "running"
    LLM = "llm"
    TOOL = "tool"
    WAITING_ON_TOOL = "waiting_on_tool"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OrchestrationQueuePolicy(StrEnum):
    FIFO = "fifo"
    JUMP_QUEUE = "jump_queue"
    LANE_JUMP_QUEUE = "lane_jump_queue"
    RESUME_FIRST = "resume_first"


@dataclass(frozen=True, slots=True)
class InboundInstruction(ValueObject):
    source: str
    content: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise OrchestrationValidationError("Inbound instruction source cannot be empty.")
        object.__setattr__(self, "content", self.content if self.content is None else str(self.content))
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source": self.source,
            "metadata": dict(self.metadata),
        }
        if self.content is not None:
            payload["content"] = self.content
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "InboundInstruction":
        payload = payload or {}
        return cls(
            source=str(payload.get("source", "")),
            content=(
                str(payload["content"])
                if payload.get("content") is not None
                else None
            ),
            metadata=(
                dict(payload.get("metadata"))
                if isinstance(payload.get("metadata"), dict)
                else {}
            ),
        )


@dataclass(frozen=True, slots=True)
class DeliveryTarget(ValueObject):
    interface_name: str
    address: str | None = None
    reply_to: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.interface_name.strip():
            raise OrchestrationValidationError("Delivery target interface_name cannot be empty.")
        object.__setattr__(self, "address", self.address if self.address is None else str(self.address))
        object.__setattr__(self, "reply_to", self.reply_to if self.reply_to is None else str(self.reply_to))
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "interface_name": self.interface_name,
            "metadata": dict(self.metadata),
        }
        if self.address is not None:
            payload["address"] = self.address
        if self.reply_to is not None:
            payload["reply_to"] = self.reply_to
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "DeliveryTarget | None":
        if not payload:
            return None
        return cls(
            interface_name=str(payload.get("interface_name", "")),
            address=(
                str(payload["address"])
                if payload.get("address") is not None
                else None
            ),
            reply_to=(
                str(payload["reply_to"])
                if payload.get("reply_to") is not None
                else None
            ),
            metadata=(
                dict(payload.get("metadata"))
                if isinstance(payload.get("metadata"), dict)
                else {}
            ),
        )


@dataclass(frozen=True, slots=True)
class OrchestrationErrorPayload(ValueObject):
    message: str
    code: str = "orchestration_failed"
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.message.strip():
            raise OrchestrationValidationError(
                "Orchestration error payload message cannot be empty.",
            )
        if not self.code.strip():
            raise OrchestrationValidationError(
                "Orchestration error payload code cannot be empty.",
            )
        object.__setattr__(self, "details", dict(self.details))

    def to_payload(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "code": self.code,
            "details": dict(self.details),
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
    ) -> "OrchestrationErrorPayload | None":
        if not payload:
            return None
        return cls(
            message=str(payload.get("message", "")),
            code=str(payload.get("code", "orchestration_failed")),
            details=(
                dict(payload.get("details"))
                if isinstance(payload.get("details"), dict)
                else {}
            ),
        )
