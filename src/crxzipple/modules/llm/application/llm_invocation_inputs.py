from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from crxzipple.modules.llm.application.runtime_request import RuntimeLlmRequest
from crxzipple.modules.llm.domain import (
    LlmInputItem,
    LlmInputItemKind,
    LlmMessage,
    LlmProviderContinuation,
    ToolSchema,
)


def _runtime_input_items_from_messages(
    messages: tuple[LlmMessage, ...],
) -> tuple[LlmInputItem, ...]:
    return tuple(
        LlmInputItem(
            kind=LlmInputItemKind.MESSAGE,
            payload={"role": message.role.value, "content": message.content},
        )
        for message in messages
        if message.role.value != "system"
    )


def runtime_invocation_references(
    *,
    request_metadata: dict[str, Any],
    runtime_context: dict[str, Any],
    runtime_route: dict[str, Any],
) -> dict[str, str | None]:
    return {
        "run_id": _first_metadata_text(
            request_metadata.get("run_id"),
            _mapping_value(request_metadata.get("runtime_context"), "run_id"),
            runtime_context.get("run_id"),
        ),
        "agent_id": _first_metadata_text(
            request_metadata.get("agent_id"),
            _mapping_value(request_metadata.get("runtime_context"), "agent_id"),
            runtime_context.get("agent_id"),
        ),
        "session_key": _first_metadata_text(
            request_metadata.get("session_key"),
            _mapping_value(request_metadata.get("runtime_context"), "session_key"),
            runtime_route.get("session_key"),
        ),
        "active_session_id": _first_metadata_text(
            request_metadata.get("active_session_id"),
            _mapping_value(
                request_metadata.get("runtime_context"),
                "active_session_id",
            ),
            runtime_route.get("active_session_id"),
        ),
    }


def _mapping_value(value: object, key: str) -> object:
    if isinstance(value, dict):
        return value.get(key)
    return None


def _first_metadata_text(*values: object) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


@dataclass(frozen=True, slots=True)
class InvokeLlmInput:
    llm_id: str
    messages: tuple[LlmMessage, ...]
    input_items: tuple[LlmInputItem, ...] = field(default_factory=tuple)
    provider_context_messages: tuple[LlmMessage, ...] = field(default_factory=tuple)
    tool_schemas: tuple[ToolSchema, ...] = field(default_factory=tuple)
    response_format: dict[str, Any] | None = None
    request_policy: dict[str, Any] = field(default_factory=dict)
    overrides: dict[str, Any] = field(default_factory=dict)
    request_metadata: dict[str, Any] = field(default_factory=dict)
    runtime_context: dict[str, Any] = field(default_factory=dict)
    runtime_route: dict[str, Any] = field(default_factory=dict)
    runtime_policy: dict[str, Any] = field(default_factory=dict)
    invocation_id: str | None = None
    continuation: LlmProviderContinuation | None = None

    def __post_init__(self) -> None:
        if not self.input_items:
            object.__setattr__(
                self,
                "input_items",
                _runtime_input_items_from_messages(self.messages),
            )

    @classmethod
    def from_runtime_request(
        cls,
        request: RuntimeLlmRequest,
        *,
        response_format: dict[str, Any] | None = None,
        overrides: dict[str, Any] | None = None,
        invocation_id: str | None = None,
        continuation: LlmProviderContinuation | None = None,
    ) -> "InvokeLlmInput":
        return cls(
            llm_id=request.llm_id,
            messages=request.messages,
            input_items=request.transcript.items,
            provider_context_messages=request.provider_context_messages,
            tool_schemas=request.tool_schemas,
            response_format=(
                dict(response_format)
                if response_format is not None
                else request.response_format()
            ),
            request_policy=dict(request.transcript.policy),
            overrides=dict(
                overrides if overrides is not None else request.provider_overrides(),
            ),
            request_metadata=request.request_metadata(),
            runtime_context=request.renderer_context().to_payload(),
            runtime_route=request.renderer_route().to_payload(),
            runtime_policy=request.renderer_policy().to_payload(),
            invocation_id=invocation_id,
            continuation=continuation,
        )


@dataclass(frozen=True, slots=True)
class StreamLlmInput:
    llm_id: str
    messages: tuple[LlmMessage, ...]
    input_items: tuple[LlmInputItem, ...] = field(default_factory=tuple)
    provider_context_messages: tuple[LlmMessage, ...] = field(default_factory=tuple)
    tool_schemas: tuple[ToolSchema, ...] = field(default_factory=tuple)
    response_format: dict[str, Any] | None = None
    request_policy: dict[str, Any] = field(default_factory=dict)
    overrides: dict[str, Any] = field(default_factory=dict)
    request_metadata: dict[str, Any] = field(default_factory=dict)
    runtime_context: dict[str, Any] = field(default_factory=dict)
    runtime_route: dict[str, Any] = field(default_factory=dict)
    runtime_policy: dict[str, Any] = field(default_factory=dict)
    invocation_id: str | None = None
    continuation: LlmProviderContinuation | None = None

    def __post_init__(self) -> None:
        if not self.input_items:
            object.__setattr__(
                self,
                "input_items",
                _runtime_input_items_from_messages(self.messages),
            )

    @classmethod
    def from_runtime_request(
        cls,
        request: RuntimeLlmRequest,
        *,
        response_format: dict[str, Any] | None = None,
        overrides: dict[str, Any] | None = None,
        invocation_id: str | None = None,
        continuation: LlmProviderContinuation | None = None,
    ) -> "StreamLlmInput":
        return cls(
            llm_id=request.llm_id,
            messages=request.messages,
            input_items=request.transcript.items,
            provider_context_messages=request.provider_context_messages,
            tool_schemas=request.tool_schemas,
            response_format=(
                dict(response_format)
                if response_format is not None
                else request.response_format()
            ),
            request_policy=dict(request.transcript.policy),
            overrides=dict(
                overrides if overrides is not None else request.provider_overrides(),
            ),
            request_metadata=request.request_metadata(),
            runtime_context=request.renderer_context().to_payload(),
            runtime_route=request.renderer_route().to_payload(),
            runtime_policy=request.renderer_policy().to_payload(),
            invocation_id=invocation_id,
            continuation=continuation,
        )


@dataclass(frozen=True, slots=True)
class WarmupLlmProfileInput:
    llm_id: str


@dataclass(frozen=True, slots=True)
class WarmupLlmProfileResult:
    llm_id: str
    status: str
    details: dict[str, Any] = field(default_factory=dict)
