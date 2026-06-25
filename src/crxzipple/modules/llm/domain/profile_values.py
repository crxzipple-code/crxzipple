from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from crxzipple.modules.llm.domain.exceptions import LlmValidationError
from crxzipple.shared.domain import ValueObject


@dataclass(frozen=True, slots=True)
class LlmDefaults(ValueObject):
    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None
    reasoning_effort: str | None = None
    provider_transport: str | None = None
    extra_body: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.max_output_tokens is not None and self.max_output_tokens <= 0:
            raise LlmValidationError(
                "LLM max_output_tokens must be greater than zero.",
            )
        if self.provider_transport is not None:
            normalized_transport = self.provider_transport.strip().lower()
            if normalized_transport not in {"auto", "http", "websocket"}:
                raise LlmValidationError(
                    "LLM provider_transport must be auto, http, or websocket.",
                )
            object.__setattr__(self, "provider_transport", normalized_transport)
        object.__setattr__(self, "extra_body", dict(self.extra_body))

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        if self.top_p is not None:
            payload["top_p"] = self.top_p
        if self.max_output_tokens is not None:
            payload["max_output_tokens"] = self.max_output_tokens
        if self.reasoning_effort is not None:
            payload["reasoning_effort"] = self.reasoning_effort
        if self.provider_transport is not None:
            payload["provider_transport"] = self.provider_transport
        if self.extra_body:
            payload["extra_body"] = dict(self.extra_body)
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "LlmDefaults":
        payload = payload or {}
        extra_body_raw = payload.get("extra_body")
        if extra_body_raw is None:
            extra_body: dict[str, Any] = {}
        elif isinstance(extra_body_raw, dict):
            extra_body = dict(extra_body_raw)
        else:
            raise LlmValidationError("LLM extra_body must decode to an object.")
        return cls(
            temperature=(
                float(payload["temperature"])
                if payload.get("temperature") is not None
                else None
            ),
            top_p=float(payload["top_p"]) if payload.get("top_p") is not None else None,
            max_output_tokens=(
                int(payload["max_output_tokens"])
                if payload.get("max_output_tokens") is not None
                else None
            ),
            reasoning_effort=(
                str(payload["reasoning_effort"])
                if payload.get("reasoning_effort") is not None
                else None
            ),
            provider_transport=(
                str(payload["provider_transport"])
                if payload.get("provider_transport") is not None
                else None
            ),
            extra_body=extra_body,
        )


__all__ = ["LlmDefaults"]
