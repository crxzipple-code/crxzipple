from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from crxzipple.modules.llm.domain.exceptions import LlmValidationError
from crxzipple.shared.domain import ValueObject


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LlmProviderKind(StrEnum):
    OPENAI = "openai"
    OPENAI_CODEX = "openai_codex"
    OPENAI_COMPATIBLE = "openai_compatible"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OLLAMA = "ollama"


class LlmApiFamily(StrEnum):
    OPENAI_RESPONSES = "openai_responses"
    OPENAI_CODEX_RESPONSES = "openai_codex_responses"
    OPENAI_CHAT_COMPATIBLE = "openai_chat_compatible"
    ANTHROPIC_MESSAGES = "anthropic_messages"
    GEMINI_GENERATE_CONTENT = "gemini_generate_content"
    OLLAMA_NATIVE = "ollama_native"


class LlmModelFamily(StrEnum):
    GENERAL = "general"
    CODEX = "codex"
    REASONING = "reasoning"
    VISION = "vision"


class LlmCapability(StrEnum):
    TOOL_CALLING = "tool_calling"
    STRUCTURED_OUTPUT = "structured_output"
    VISION_INPUT = "vision_input"
    STREAMING = "streaming"
    REASONING = "reasoning"


class LlmSourceKind(StrEnum):
    MANUAL = "manual"
    DISCOVERED = "discovered"
    IMPORTED = "imported"


class LlmInvocationStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class LlmMessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True, slots=True)
class LlmDefaults(ValueObject):
    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None
    reasoning_effort: str | None = None
    extra_body: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.max_output_tokens is not None and self.max_output_tokens <= 0:
            raise LlmValidationError(
                "LLM max_output_tokens must be greater than zero.",
            )
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
            extra_body=extra_body,
        )


@dataclass(frozen=True, slots=True)
class LlmMessage(ValueObject):
    role: LlmMessageRole
    content: Any
    name: str | None = None
    tool_call_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "role": self.role.value,
            "content": self.content,
        }
        if self.name is not None:
            payload["name"] = self.name
        if self.tool_call_id is not None:
            payload["tool_call_id"] = self.tool_call_id
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "LlmMessage":
        return cls(
            role=LlmMessageRole(payload["role"]),
            content=payload.get("content"),
            name=payload.get("name"),
            tool_call_id=payload.get("tool_call_id"),
            metadata=(
                dict(payload.get("metadata"))
                if isinstance(payload.get("metadata"), dict)
                else {}
            ),
        )


@dataclass(frozen=True, slots=True)
class ToolSchema(ValueObject):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise LlmValidationError("Tool schema name cannot be empty.")
        object.__setattr__(self, "input_schema", dict(self.input_schema))

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": dict(self.input_schema),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ToolSchema":
        return cls(
            name=str(payload.get("name", "")),
            description=str(payload.get("description", "")),
            input_schema=(
                dict(payload.get("input_schema"))
                if isinstance(payload.get("input_schema"), dict)
                else {}
            ),
        )


@dataclass(frozen=True, slots=True)
class ToolCallIntent(ValueObject):
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise LlmValidationError("Tool call id cannot be empty.")
        if not self.name.strip():
            raise LlmValidationError("Tool call name cannot be empty.")
        object.__setattr__(self, "arguments", dict(self.arguments))

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "arguments": dict(self.arguments),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ToolCallIntent":
        return cls(
            id=str(payload.get("id", "")),
            name=str(payload.get("name", "")),
            arguments=(
                dict(payload.get("arguments"))
                if isinstance(payload.get("arguments"), dict)
                else {}
            ),
        )


@dataclass(frozen=True, slots=True)
class LlmUsage(ValueObject):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.input_tokens is not None:
            payload["input_tokens"] = self.input_tokens
        if self.output_tokens is not None:
            payload["output_tokens"] = self.output_tokens
        if self.total_tokens is not None:
            payload["total_tokens"] = self.total_tokens
        if self.reasoning_tokens is not None:
            payload["reasoning_tokens"] = self.reasoning_tokens
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "LlmUsage | None":
        if not payload:
            return None
        return cls(
            input_tokens=(
                int(payload["input_tokens"])
                if payload.get("input_tokens") is not None
                else None
            ),
            output_tokens=(
                int(payload["output_tokens"])
                if payload.get("output_tokens") is not None
                else None
            ),
            total_tokens=(
                int(payload["total_tokens"])
                if payload.get("total_tokens") is not None
                else None
            ),
            reasoning_tokens=(
                int(payload["reasoning_tokens"])
                if payload.get("reasoning_tokens") is not None
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class LlmResult(ValueObject):
    text: str | None = None
    tool_calls: tuple[ToolCallIntent, ...] = field(default_factory=tuple)
    structured_output: Any | None = None
    usage: LlmUsage | None = None
    finish_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_calls", tuple(self.tool_calls))
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "tool_calls": [tool_call.to_payload() for tool_call in self.tool_calls],
            "metadata": dict(self.metadata),
        }
        if self.text is not None:
            payload["text"] = self.text
        if self.structured_output is not None:
            payload["structured_output"] = self.structured_output
        if self.usage is not None:
            payload["usage"] = self.usage.to_payload()
        if self.finish_reason is not None:
            payload["finish_reason"] = self.finish_reason
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "LlmResult | None":
        if not payload:
            return None
        tool_calls_raw = payload.get("tool_calls")
        return cls(
            text=payload.get("text"),
            tool_calls=tuple(
                ToolCallIntent.from_payload(item)
                for item in tool_calls_raw
                if isinstance(item, dict)
            )
            if isinstance(tool_calls_raw, list)
            else (),
            structured_output=payload.get("structured_output"),
            usage=LlmUsage.from_payload(payload.get("usage")),
            finish_reason=payload.get("finish_reason"),
            metadata=(
                dict(payload.get("metadata"))
                if isinstance(payload.get("metadata"), dict)
                else {}
            ),
        )


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
