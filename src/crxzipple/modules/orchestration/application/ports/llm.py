from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Protocol

from crxzipple.modules.llm.application import InvokeLlmInput, StreamLlmInput
from crxzipple.modules.llm.application.streaming import LlmStreamEvent
from crxzipple.modules.llm.domain import LlmInvocation, LlmProfile


class LlmPort(Protocol):
    def get_profile(self, llm_id: str) -> LlmProfile:
        ...

    def invoke(self, data: InvokeLlmInput) -> LlmInvocation:
        ...

    async def invoke_async(self, data: InvokeLlmInput) -> LlmInvocation:
        ...

    def stream_invoke(self, data: StreamLlmInput) -> Iterator[LlmStreamEvent]:
        ...

    def stream_invoke_async(
        self,
        data: StreamLlmInput,
    ) -> AsyncIterator[LlmStreamEvent]:
        ...

    def get_invocation(self, invocation_id: str) -> LlmInvocation:
        ...
