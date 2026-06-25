from __future__ import annotations

from crxzipple.modules.llm.application.adapters import LlmAdapterResponse
from crxzipple.modules.llm.application.streaming import LlmStreamEvent
from crxzipple.modules.llm.domain import LlmResult
from crxzipple.modules.llm.infrastructure.adapters.openai_codex_event_projection import (
    codex_continuation_from_completed_event,
    codex_response_items_from_completed_event,
)


def codex_adapter_response_from_completed_event(
    completed_event: LlmStreamEvent | None,
    *,
    description: str,
) -> LlmAdapterResponse:
    if completed_event is None:
        raise RuntimeError(f"{description} did not complete.")
    result_payload = completed_event.data.get("result")
    if not isinstance(result_payload, dict):
        raise RuntimeError(f"{description} completed without a result payload.")
    result = LlmResult.from_payload(result_payload)
    if result is None:
        raise RuntimeError(f"{description} completed with an invalid result payload.")
    provider_request_id = completed_event.data.get("provider_request_id")
    response_items = codex_response_items_from_completed_event(completed_event)
    return LlmAdapterResponse(
        result=result,
        response_items=response_items,
        continuation=codex_continuation_from_completed_event(completed_event),
        provider_request_id=(
            str(provider_request_id) if provider_request_id is not None else None
        ),
    )
