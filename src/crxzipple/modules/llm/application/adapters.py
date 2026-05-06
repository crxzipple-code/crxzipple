from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.domain.value_objects import (
    LlmApiFamily,
    LlmMessage,
    LlmResult,
    ToolSchema,
)
from crxzipple.modules.llm.application.streaming import LlmStreamEvent


@dataclass(frozen=True, slots=True)
class LlmAdapterRequest:
    messages: tuple[LlmMessage, ...]
    tool_schemas: tuple[ToolSchema, ...] = field(default_factory=tuple)
    response_format: dict[str, Any] | None = None
    overrides: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LlmAdapterResponse:
    result: LlmResult
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


class LlmAdapterGateway(Protocol):
    def get(self, api_family: LlmApiFamily) -> LlmAdapter | None:
        ...
