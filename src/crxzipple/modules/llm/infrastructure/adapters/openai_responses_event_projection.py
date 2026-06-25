from __future__ import annotations

import json
from typing import Any

from crxzipple.modules.llm.application.adapters import LlmAdapterResponse
from crxzipple.modules.llm.application.streaming import LlmStreamEvent
from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.domain import (
    LlmContinuationSignal,
    LlmResponseItem,
    LlmResult,
    LlmUsage,
)
from crxzipple.modules.llm.infrastructure.adapters.http_helpers import (
    RetryableOpenAIStreamError,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_response_projection import (
    build_openai_continuation_signal,
    build_openai_response_items,
    openai_response_stream_event,
)


def openai_responses_response_items_from_completed_event(
    event: LlmStreamEvent,
) -> tuple[LlmResponseItem, ...]:
    raw_items = event.data.get("response_items")
    if not isinstance(raw_items, list):
        return ()
    return tuple(
        LlmResponseItem.from_payload(item)
        for item in raw_items
        if isinstance(item, dict)
    )


def openai_responses_continuation_from_completed_event(
    event: LlmStreamEvent,
) -> LlmContinuationSignal | None:
    payload = event.data.get("continuation")
    if not isinstance(payload, dict):
        return None
    return LlmContinuationSignal.from_payload(payload)


def consume_openai_responses_event(
    profile: LlmProfile,
    event_name: str | None,
    data_lines: list[str],
    *,
    sequence: int,
    description: str,
    invocation_id: str,
    tool_name_aliases: dict[str, str] | None = None,
    completed_output_items: dict[int, dict[str, Any]] | None = None,
) -> tuple[LlmStreamEvent | None, bool]:
    if not data_lines:
        return None, False
    payload_text = "\n".join(data_lines)
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"{description} returned invalid SSE JSON: {payload_text}",
        ) from exc
    if not isinstance(payload, dict):
        return None, False

    resolved_event_name = (
        event_name
        if isinstance(event_name, str) and event_name.strip()
        else payload.get("type")
        if isinstance(payload.get("type"), str)
        else None
    )

    response_payload = payload.get("response")
    if resolved_event_name == "response.completed":
        if isinstance(response_payload, dict):
            normalized_response_payload = dict(response_payload)
            if (
                completed_output_items
                and not normalized_response_payload.get("output")
            ):
                normalized_response_payload["output"] = [
                    dict(item)
                    for _, item in sorted(completed_output_items.items())
                ]
            response = _build_openai_responses_response(
                profile,
                normalized_response_payload,
                invocation_id=invocation_id,
                tool_name_aliases=tool_name_aliases,
            )
            return (
                LlmStreamEvent(
                    type="completed",
                    sequence=sequence,
                    data={
                        "result": response.result.to_payload(),
                        "response_items": [
                            item.to_payload() for item in response.response_items
                        ],
                        "continuation": (
                            response.continuation.to_payload()
                            if response.continuation is not None
                            else None
                        ),
                        "provider_request_id": response.provider_request_id,
                    },
                ),
                True,
            )
        return None, True

    if resolved_event_name in {
        "response.output_item.added",
        "response.output_item.created",
        "response.output_item.done",
        "response.reasoning_summary_text.delta",
        "response.reasoning_summary.delta",
        "response.reasoning_text.delta",
        "response.reasoning.delta",
        "response.function_call_arguments.delta",
        "response.tool_call_arguments.delta",
    }:
        if resolved_event_name == "response.output_item.done":
            output_index = payload.get("output_index")
            item = payload.get("item")
            if (
                completed_output_items is not None
                and isinstance(output_index, int)
                and isinstance(item, dict)
            ):
                completed_output_items[output_index] = dict(item)
        return (
            openai_response_stream_event(
                event_name=resolved_event_name,
                payload=payload,
                sequence=sequence,
            ),
            False,
        )

    if payload.get("type") == "error":
        error_payload = payload.get("error")
        message = payload.get("message")
        if isinstance(error_payload, dict):
            message = error_payload.get("message") or message
            if error_payload.get("code") == "server_error":
                raise RetryableOpenAIStreamError(
                    f"{description} returned an error event: {message or payload}",
                )
        raise RuntimeError(
            f"{description} returned an error event: {message or payload}",
        )

    if resolved_event_name == "response.output_text.delta":
        delta = payload.get("delta")
        if delta is None:
            delta = payload.get("text")
        if delta is not None:
            return (
                LlmStreamEvent(
                    type="text_delta",
                    sequence=sequence,
                    data={"text": str(delta)},
                ),
                False,
            )

    return None, False


def _build_openai_responses_response(
    profile: LlmProfile,
    data: dict[str, Any],
    *,
    invocation_id: str,
    tool_name_aliases: dict[str, str] | None = None,
) -> LlmAdapterResponse:
    output = data.get("output") if isinstance(data.get("output"), list) else []
    text_fragments: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "function_call":
            continue
        if item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "output_text" and block.get("text") is not None:
                text_fragments.append(str(block.get("text")))

    usage_raw = data.get("usage")
    usage = None
    if isinstance(usage_raw, dict):
        usage = LlmUsage(
            input_tokens=usage_raw.get("input_tokens"),
            output_tokens=usage_raw.get("output_tokens"),
            total_tokens=usage_raw.get("total_tokens"),
        )

    response_items = build_openai_response_items(
        invocation_id=invocation_id,
        response_payload=data,
        tool_name_aliases=tool_name_aliases,
    )
    return LlmAdapterResponse(
        result=LlmResult.from_response_items(
            response_items,
            usage=usage,
            finish_reason=(
                str(data.get("status")) if data.get("status") is not None else None
            ),
            metadata={
                "provider": profile.provider.value,
                "response_id": data.get("id"),
                "model": data.get("model"),
                "transport": "sse",
            },
            text_fallback=data.get("output_text") or "".join(text_fragments) or None,
        ),
        response_items=response_items,
        continuation=build_openai_continuation_signal(data, response_items),
        provider_request_id=str(data.get("id")) if data.get("id") is not None else None,
    )
