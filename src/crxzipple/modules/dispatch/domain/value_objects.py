from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from crxzipple.modules.dispatch.domain.exceptions import DispatchValidationError
from crxzipple.shared.domain import ValueObject


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def validate_lease_seconds(lease_seconds: int) -> int:
    if lease_seconds <= 0:
        raise DispatchValidationError(
            "Dispatch lease_seconds must be greater than zero.",
        )
    return lease_seconds


class DispatchTaskStatus(StrEnum):
    CREATED = "created"
    QUEUED = "queued"
    CLAIMED = "claimed"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DispatchPolicy(StrEnum):
    FIFO = "fifo"
    LANE_JUMP_QUEUE = "lane_jump_queue"
    JUMP_QUEUE = "jump_queue"
    RESUME_FIRST = "resume_first"


@dataclass(frozen=True, slots=True)
class DispatchErrorPayload(ValueObject):
    message: str
    code: str = "dispatch_failed"
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.message.strip():
            raise DispatchValidationError("Dispatch error payload message cannot be empty.")
        if not self.code.strip():
            raise DispatchValidationError("Dispatch error payload code cannot be empty.")
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
    ) -> "DispatchErrorPayload | None":
        if not payload:
            return None
        return cls(
            message=str(payload.get("message", "")),
            code=str(payload.get("code", "dispatch_failed")),
            details=(
                dict(payload.get("details"))
                if isinstance(payload.get("details"), dict)
                else {}
            ),
        )
