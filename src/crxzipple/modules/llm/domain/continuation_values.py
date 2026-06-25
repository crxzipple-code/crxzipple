from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from crxzipple.modules.llm.domain.enums import LlmContinuationReason
from crxzipple.modules.llm.domain.exceptions import LlmValidationError
from crxzipple.shared.domain import ValueObject


@dataclass(frozen=True, slots=True)
class LlmContinuationSignal(ValueObject):
    end_turn: bool | None = None
    needs_follow_up: bool = False
    reason: LlmContinuationReason = LlmContinuationReason.NONE
    provider_payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_payload", dict(self.provider_payload))

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "needs_follow_up": self.needs_follow_up,
            "reason": self.reason.value,
            "provider_payload": dict(self.provider_payload),
        }
        if self.end_turn is not None:
            payload["end_turn"] = self.end_turn
        return payload

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
    ) -> "LlmContinuationSignal | None":
        if not payload:
            return None
        return cls(
            end_turn=(
                bool(payload["end_turn"]) if payload.get("end_turn") is not None else None
            ),
            needs_follow_up=bool(payload.get("needs_follow_up", False)),
            reason=LlmContinuationReason(
                str(payload.get("reason", LlmContinuationReason.NONE)),
            ),
            provider_payload=(
                dict(payload.get("provider_payload"))
                if isinstance(payload.get("provider_payload"), dict)
                else {}
            ),
        )


@dataclass(frozen=True, slots=True)
class LlmProviderContinuation(ValueObject):
    mode: str
    previous_response_id: str | None = None
    previous_invocation_id: str | None = None
    provider_family: str | None = None
    transport: str | None = None
    input_item_fingerprints: tuple[str, ...] = field(default_factory=tuple)
    input_item_count: int | None = None
    instructions_fingerprint: str | None = None
    tool_fingerprints: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        mode = self.mode.strip()
        if not mode:
            raise LlmValidationError("LLM provider continuation mode cannot be empty.")
        object.__setattr__(self, "mode", mode)
        object.__setattr__(
            self,
            "previous_response_id",
            _optional_stripped_text(self.previous_response_id),
        )
        object.__setattr__(
            self,
            "previous_invocation_id",
            _optional_stripped_text(self.previous_invocation_id),
        )
        object.__setattr__(
            self,
            "provider_family",
            _optional_stripped_text(self.provider_family),
        )
        object.__setattr__(
            self,
            "transport",
            _optional_stripped_text(self.transport),
        )
        object.__setattr__(
            self,
            "input_item_fingerprints",
            tuple(
                fingerprint.strip()
                for fingerprint in self.input_item_fingerprints
                if isinstance(fingerprint, str) and fingerprint.strip()
            ),
        )
        object.__setattr__(
            self,
            "instructions_fingerprint",
            _optional_stripped_text(self.instructions_fingerprint),
        )
        object.__setattr__(
            self,
            "tool_fingerprints",
            tuple(
                fingerprint.strip()
                for fingerprint in self.tool_fingerprints
                if isinstance(fingerprint, str) and fingerprint.strip()
            ),
        )
        if self.input_item_count is not None and self.input_item_count < 0:
            raise LlmValidationError(
                "LLM provider continuation input_item_count cannot be negative.",
            )

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"mode": self.mode}
        if self.previous_response_id is not None:
            payload["previous_response_id"] = self.previous_response_id
        if self.previous_invocation_id is not None:
            payload["previous_invocation_id"] = self.previous_invocation_id
        if self.provider_family is not None:
            payload["provider_family"] = self.provider_family
        if self.transport is not None:
            payload["transport"] = self.transport
        if self.input_item_fingerprints:
            payload["input_item_fingerprints"] = list(self.input_item_fingerprints)
        if self.input_item_count is not None:
            payload["input_item_count"] = self.input_item_count
        if self.instructions_fingerprint is not None:
            payload["instructions_fingerprint"] = self.instructions_fingerprint
        if self.tool_fingerprints:
            payload["tool_fingerprints"] = list(self.tool_fingerprints)
        return payload

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
    ) -> "LlmProviderContinuation | None":
        if not payload:
            return None
        return cls(
            mode=str(payload.get("mode") or ""),
            previous_response_id=(
                str(payload["previous_response_id"])
                if payload.get("previous_response_id") is not None
                else None
            ),
            previous_invocation_id=(
                str(payload["previous_invocation_id"])
                if payload.get("previous_invocation_id") is not None
                else None
            ),
            provider_family=(
                str(payload["provider_family"])
                if payload.get("provider_family") is not None
                else None
            ),
            transport=(
                str(payload["transport"])
                if payload.get("transport") is not None
                else None
            ),
            input_item_fingerprints=tuple(
                str(item)
                for item in payload.get("input_item_fingerprints", ())
                if isinstance(item, str) and item.strip()
            )
            if isinstance(payload.get("input_item_fingerprints"), list | tuple)
            else (),
            input_item_count=(
                int(payload["input_item_count"])
                if payload.get("input_item_count") is not None
                else None
            ),
            instructions_fingerprint=(
                str(payload["instructions_fingerprint"])
                if payload.get("instructions_fingerprint") is not None
                else None
            ),
            tool_fingerprints=tuple(
                str(item)
                for item in payload.get("tool_fingerprints", ())
                if isinstance(item, str) and item.strip()
            )
            if isinstance(payload.get("tool_fingerprints"), list | tuple)
            else (),
        )


def _optional_stripped_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


__all__ = ["LlmContinuationSignal", "LlmProviderContinuation"]
