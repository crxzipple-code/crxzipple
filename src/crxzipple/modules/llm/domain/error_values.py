from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from crxzipple.modules.llm.domain.exceptions import LlmValidationError
from crxzipple.shared.domain import ValueObject


@dataclass(frozen=True, slots=True)
class LlmErrorPayload(ValueObject):
    message: str
    code: str = "invocation_failed"
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.message.strip():
            raise LlmValidationError("LLM error message cannot be empty.")
        if not self.code.strip():
            raise LlmValidationError("LLM error code cannot be empty.")
        object.__setattr__(self, "details", dict(self.details))

    def to_payload(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "code": self.code,
            "details": dict(self.details),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "LlmErrorPayload | None":
        if not payload:
            return None
        return cls(
            message=str(payload.get("message", "")).strip(),
            code=str(payload.get("code", "invocation_failed")).strip()
            or "invocation_failed",
            details=(
                dict(payload.get("details"))
                if isinstance(payload.get("details"), dict)
                else {}
            ),
        )


__all__ = ["LlmErrorPayload"]
