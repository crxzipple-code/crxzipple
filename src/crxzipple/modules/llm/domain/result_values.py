from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from crxzipple.modules.llm.domain.enums import LlmResponseItemKind
from crxzipple.modules.llm.domain.exceptions import LlmValidationError
from crxzipple.shared.domain import ValueObject


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

    @classmethod
    def from_response_items(
        cls,
        response_items: tuple[Any, ...],
        *,
        usage: LlmUsage | None = None,
        finish_reason: str | None = None,
        metadata: dict[str, Any] | None = None,
        structured_output: Any | None = None,
        text_fallback: str | None = None,
    ) -> "LlmResult":
        text_fragments: list[str] = []
        tool_calls: list[ToolCallIntent] = []
        for item in response_items:
            if item.kind is LlmResponseItemKind.ASSISTANT_MESSAGE:
                text = _response_item_text(item)
                if text is not None:
                    text_fragments.append(text)
                continue
            if item.kind is LlmResponseItemKind.TOOL_CALL and item.tool_name:
                arguments = item.content_payload.get("arguments")
                tool_calls.append(
                    ToolCallIntent(
                        id=item.call_id or item.provider_item_id or item.id,
                        name=item.tool_name,
                        arguments=dict(arguments) if isinstance(arguments, dict) else {},
                    ),
                )
        text = "".join(text_fragments) or text_fallback
        return cls(
            text=text or None,
            tool_calls=tuple(tool_calls),
            structured_output=structured_output,
            usage=usage,
            finish_reason=finish_reason,
            metadata=dict(metadata or {}),
        )


def _response_item_text(item: Any) -> str | None:
    text = item.content_payload.get("text")
    if text is not None:
        return str(text)
    summary = item.content_payload.get("summary")
    if isinstance(summary, str):
        return summary
    if isinstance(summary, list):
        fragments: list[str] = []
        for block in summary:
            if isinstance(block, dict) and block.get("text") is not None:
                fragments.append(str(block.get("text")))
            elif isinstance(block, str):
                fragments.append(block)
        return "".join(fragments) or None
    return None


__all__ = ["LlmResult", "LlmUsage", "ToolCallIntent"]
