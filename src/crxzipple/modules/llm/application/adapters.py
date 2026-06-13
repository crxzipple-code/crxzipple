from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.domain.value_objects import (
    LlmApiFamily,
    LlmContinuationSignal,
    LlmMessage,
    LlmProviderContinuation,
    LlmResponseItem,
    LlmResult,
    ToolSchema,
)
from crxzipple.modules.llm.application.streaming import LlmStreamEvent


@dataclass(frozen=True, slots=True)
class LlmAdapterRequest:
    invocation_id: str
    messages: tuple[LlmMessage, ...]
    tool_schemas: tuple[ToolSchema, ...] = field(default_factory=tuple)
    response_format: dict[str, Any] | None = None
    overrides: dict[str, Any] = field(default_factory=dict)
    resolved_credential: str | None = None
    continuation: LlmProviderContinuation | None = None


@dataclass(frozen=True, slots=True)
class LlmAdapterResponse:
    result: LlmResult
    response_items: tuple[LlmResponseItem, ...] = field(default_factory=tuple)
    continuation: LlmContinuationSignal | None = None
    provider_request_id: str | None = None


class LlmAdapter(Protocol):
    def invoke(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> LlmAdapterResponse:
        ...


class AsyncLlmAdapter(Protocol):
    async def invoke_async(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> LlmAdapterResponse:
        ...


class LlmStreamingAdapter(Protocol):
    def stream_invoke(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> Iterator[LlmStreamEvent]:
        ...


class AsyncLlmStreamingAdapter(Protocol):
    def stream_invoke_async(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> AsyncIterator[LlmStreamEvent]:
        ...


class LlmRequestPreviewAdapter(Protocol):
    def preview_request(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> dict[str, Any]:
        ...


class LlmAdapterGateway(Protocol):
    def get(self, api_family: LlmApiFamily) -> LlmAdapter | None:
        ...
