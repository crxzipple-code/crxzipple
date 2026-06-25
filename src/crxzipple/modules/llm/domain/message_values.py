from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from crxzipple.modules.llm.domain.enums import (
    LlmInputItemKind,
    LlmMessageRole,
)
from crxzipple.modules.llm.domain.exceptions import LlmValidationError
from crxzipple.shared.domain import ValueObject


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
class LlmInputItem(ValueObject):
    kind: LlmInputItemKind
    payload: dict[str, Any]
    source: str = "projection"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", dict(self.payload))
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind.value,
            "payload": dict(self.payload),
            "source": self.source,
        }
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "LlmInputItem":
        return cls(
            kind=LlmInputItemKind(str(payload.get("kind", "message"))),
            payload=(
                dict(payload.get("payload"))
                if isinstance(payload.get("payload"), dict)
                else {}
            ),
            source=str(payload.get("source") or "projection"),
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


__all__ = ["LlmInputItem", "LlmMessage", "ToolSchema"]
