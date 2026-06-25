from __future__ import annotations

from crxzipple.modules.llm.application.llm_completed_payload import (
    continuation_from_completed_payload,
    response_items_from_completed_payload,
)
from crxzipple.modules.llm.application.llm_invocation_service import (
    LlmInvocationService,
)
from crxzipple.modules.llm.application.llm_streaming_completion_recorder import (
    LlmStreamingCompletionRecorder,
)
from crxzipple.modules.llm.application.streaming import LlmStreamEvent
from crxzipple.modules.llm.domain.entities import LlmInvocation
from crxzipple.modules.llm.domain import LlmErrorPayload, LlmResult


class LlmStreamingEventRecorder:
    def __init__(
        self,
        *,
        invocation_service: LlmInvocationService,
        streaming_completion_recorder: LlmStreamingCompletionRecorder,
    ) -> None:
        self._invocation_service = invocation_service
        self._streaming_completion_recorder = streaming_completion_recorder

    @staticmethod
    def started_event(
        invocation: LlmInvocation,
        sequence: int,
    ) -> LlmStreamEvent:
        return LlmStreamEvent(
            type="invocation_started",
            sequence=sequence,
            invocation_id=invocation.id,
            data={
                "llm_id": invocation.llm_id,
                "status": invocation.status.value,
            },
        )

    def record_started_event(
        self,
        invocation: LlmInvocation,
        *,
        sequence: int,
    ) -> None:
        self.record_response_event(
            invocation.id,
            sequence=sequence,
            event_type="invocation_started",
            data={
                "llm_id": invocation.llm_id,
                "status": invocation.status.value,
            },
        )

    @staticmethod
    def normalized_event(
        event: LlmStreamEvent,
        *,
        sequence: int,
        invocation_id: str,
    ) -> LlmStreamEvent:
        return LlmStreamEvent(
            type=event.type,
            sequence=sequence,
            invocation_id=invocation_id,
            data=dict(event.data),
        )

    def complete_from_stream_event(
        self,
        invocation_id: str,
        event: LlmStreamEvent,
    ) -> None:
        result_payload = event.data.get("result")
        response_items = response_items_from_completed_payload(event.data)
        continuation = continuation_from_completed_payload(event.data)
        provider_request_id = event.data.get("provider_request_id")
        if not isinstance(result_payload, dict):
            raise RuntimeError(
                "Streaming llm adapter completed without a result payload.",
            )
        result = LlmResult.from_payload(result_payload)
        if result is None:
            raise RuntimeError(
                "Streaming llm adapter completed with an invalid result payload.",
            )
        self._streaming_completion_recorder.complete(
            invocation_id,
            result,
            response_items=response_items,
            continuation=continuation,
            provider_request_id=(
                str(provider_request_id) if provider_request_id is not None else None
            ),
        )

    def incomplete_stream_failed_event(
        self,
        invocation_id: str,
        *,
        sequence: int,
    ) -> LlmStreamEvent:
        return self.failed_event(
            invocation_id,
            sequence=sequence,
            error=LlmErrorPayload(
                message="Streaming llm invocation ended before completion.",
                code="stream_incomplete",
            ),
        )

    def adapter_failed_event(
        self,
        invocation_id: str,
        *,
        sequence: int,
        error_message: str,
    ) -> LlmStreamEvent:
        return self.failed_event(
            invocation_id,
            sequence=sequence,
            error=LlmErrorPayload(
                message=error_message,
                code="adapter_error",
            ),
        )

    def failed_event(
        self,
        invocation_id: str,
        *,
        sequence: int,
        error: LlmErrorPayload,
    ) -> LlmStreamEvent:
        failed = self._invocation_service.fail_invocation(
            invocation_id,
            error,
            streaming=True,
        )
        data = {"error": failed.error.to_payload() if failed.error else {}}
        event = LlmStreamEvent(
            type="failed",
            sequence=sequence,
            invocation_id=invocation_id,
            data=data,
        )
        self.record_response_event(
            invocation_id,
            sequence=sequence,
            event_type="failed",
            data=data,
        )
        return event

    def record_response_event(
        self,
        invocation_id: str,
        *,
        sequence: int,
        event_type: str,
        data: dict[str, object],
    ) -> None:
        self._invocation_service.record_response_event(
            invocation_id,
            sequence=sequence,
            event_type=event_type,
            data=data,
        )


__all__ = ["LlmStreamingEventRecorder"]
