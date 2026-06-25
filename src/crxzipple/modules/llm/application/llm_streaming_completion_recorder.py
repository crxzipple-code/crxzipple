from __future__ import annotations

from crxzipple.modules.llm.application.llm_invocation_service import (
    LlmInvocationService,
)
from crxzipple.modules.llm.domain.entities import LlmInvocation
from crxzipple.modules.llm.domain import (
    LlmContinuationSignal,
    LlmResponseItem,
    LlmResult,
)


class LlmStreamingCompletionRecorder:
    def __init__(self, invocation_service: LlmInvocationService) -> None:
        self._invocation_service = invocation_service

    def complete(
        self,
        invocation_id: str,
        result: LlmResult,
        *,
        response_items: tuple[LlmResponseItem, ...] = (),
        continuation: LlmContinuationSignal | None = None,
        provider_request_id: str | None = None,
    ) -> LlmInvocation:
        return self._invocation_service.complete_invocation(
            invocation_id,
            result,
            response_items=response_items,
            continuation=continuation,
            provider_request_id=provider_request_id,
            streaming=True,
        )
