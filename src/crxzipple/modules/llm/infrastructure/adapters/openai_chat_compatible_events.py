from __future__ import annotations

from typing import Any

from crxzipple.modules.llm.application.adapters import LlmAdapterResponse
from crxzipple.modules.llm.application.streaming import LlmStreamEvent
from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.domain import (
    LlmContinuationReason,
    LlmContinuationSignal,
    LlmResponseItem,
    LlmResponseItemKind,
    LlmResult,
    LlmUsage,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_chat_compatible_response_items import (
    build_chat_response_items,
    chat_message_tool_calls_and_text,
    parse_xmlish_tool_calls,
    strip_xmlish_tool_calls,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_protocol import (
    ProviderWireRequest,
)


def build_openai_chat_adapter_response(
    profile: LlmProfile,
    *,
    invocation_id: str,
    payload: dict[str, Any],
    tool_name_aliases: dict[str, str] | None = None,
) -> LlmAdapterResponse:
    choice, message = _first_chat_choice_and_message(profile, payload)
    raw_tool_calls, content_text = chat_message_tool_calls_and_text(message)
    usage = _usage_from_chat_payload(payload)
    provider_request_id = (
        str(payload.get("id")) if payload.get("id") is not None else None
    )
    model_name = str(payload.get("model")) if payload.get("model") is not None else None
    response_items = build_chat_response_items(
        invocation_id=invocation_id,
        content_text=content_text,
        raw_tool_calls=raw_tool_calls,
        provider_response_id=provider_request_id,
        model_name=model_name,
        transport="json",
        tool_name_aliases=tool_name_aliases,
    )
    return LlmAdapterResponse(
        result=LlmResult.from_response_items(
            response_items,
            usage=usage,
            finish_reason=(
                str(choice.get("finish_reason"))
                if choice.get("finish_reason") is not None
                else None
            ),
            metadata={
                "provider": profile.provider.value,
                "response_id": payload.get("id"),
                "model": payload.get("model"),
            },
            text_fallback=content_text,
        ),
        response_items=response_items,
        provider_request_id=provider_request_id,
        continuation=build_chat_continuation_signal(
            choice,
            payload,
            response_items,
        ),
    )


def openai_chat_response_items_from_completed_event(
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


def alias_to_original_tool_names(
    wire_request: ProviderWireRequest,
) -> dict[str, str]:
    return {
        alias: original
        for original, alias in wire_request.tool_name_aliases.items()
    }


def build_json_completed_event(
    profile: LlmProfile,
    payload: dict[str, Any],
    *,
    sequence: int,
    invocation_id: str,
    tool_name_aliases: dict[str, str] | None = None,
) -> LlmStreamEvent:
    choice, message = _first_chat_choice_and_message(profile, payload)
    raw_tool_calls, content_text = chat_message_tool_calls_and_text(message)
    usage = _usage_from_chat_payload(payload)
    provider_request_id = (
        str(payload.get("id")) if payload.get("id") is not None else None
    )
    response_items = build_chat_response_items(
        invocation_id=invocation_id,
        content_text=content_text,
        raw_tool_calls=raw_tool_calls,
        provider_response_id=provider_request_id,
        model_name=str(payload.get("model")) if payload.get("model") is not None else None,
        transport="json_fallback",
        tool_name_aliases=tool_name_aliases,
    )
    result = LlmResult.from_response_items(
        response_items,
        usage=usage,
        finish_reason=(
            str(choice.get("finish_reason"))
            if choice.get("finish_reason") is not None
            else None
        ),
        metadata={
            "provider": profile.provider.value,
            "response_id": payload.get("id"),
            "model": payload.get("model"),
            "transport": "json_fallback",
        },
        text_fallback=content_text,
    )
    return LlmStreamEvent(
        type="completed",
        sequence=sequence,
        data={
            "result": result.to_payload(),
            "response_items": [item.to_payload() for item in response_items],
            "provider_request_id": provider_request_id,
            "continuation": build_chat_continuation_signal(
                choice,
                payload,
                response_items,
            ).to_payload(),
        },
    )


def merge_stream_tool_calls(
    tool_call_chunks: dict[int, dict[str, Any]],
    tool_calls: list[Any],
) -> None:
    for position, item in enumerate(tool_calls):
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("index", position))
        except (TypeError, ValueError):
            index = position
        existing = tool_call_chunks.setdefault(
            index,
            {
                "id": None,
                "name": "",
                "arguments": "",
            },
        )
        if item.get("id") is not None:
            existing["id"] = str(item.get("id"))
        function = item.get("function")
        if not isinstance(function, dict):
            continue
        if function.get("name") is not None:
            existing["name"] = f"{existing.get('name') or ''}{function.get('name')}"
        if function.get("arguments") is not None:
            existing["arguments"] = (
                f"{existing.get('arguments') or ''}{function.get('arguments')}"
            )


def build_stream_completed_event(
    profile: LlmProfile,
    *,
    sequence: int,
    invocation_id: str,
    response_id: str | None,
    model_name: str | None,
    text_fragments: list[str],
    tool_call_chunks: dict[int, dict[str, Any]],
    usage_raw: dict[str, Any] | None,
    finish_reason: str | None,
    tool_name_aliases: dict[str, str] | None = None,
) -> LlmStreamEvent:
    content_text = "".join(text_fragments) or None
    raw_tool_calls = [
        {
            "id": chunk.get("id") or f"chatcmpl-tool-{index}",
            "name": chunk.get("name"),
            "arguments": chunk.get("arguments"),
        }
        for index, chunk in sorted(tool_call_chunks.items())
        if chunk.get("name")
    ]
    if not raw_tool_calls and content_text:
        parsed_tool_calls = parse_xmlish_tool_calls(content_text)
        if parsed_tool_calls:
            raw_tool_calls.extend(parsed_tool_calls)
            content_text = strip_xmlish_tool_calls(content_text)
    usage = None
    if isinstance(usage_raw, dict):
        usage = LlmUsage(
            input_tokens=usage_raw.get("prompt_tokens"),
            output_tokens=usage_raw.get("completion_tokens"),
            total_tokens=usage_raw.get("total_tokens"),
        )
    response_items = build_chat_response_items(
        invocation_id=invocation_id,
        content_text=content_text,
        raw_tool_calls=raw_tool_calls,
        provider_response_id=response_id,
        model_name=model_name or profile.model_name,
        transport="sse",
        tool_name_aliases=tool_name_aliases,
    )
    result = LlmResult.from_response_items(
        response_items,
        usage=usage,
        finish_reason=finish_reason,
        metadata={
            "provider": profile.provider.value,
            "response_id": response_id,
            "model": model_name or profile.model_name,
            "transport": "sse",
        },
        text_fallback=content_text,
    )
    return LlmStreamEvent(
        type="completed",
        sequence=sequence,
        data={
            "result": result.to_payload(),
            "response_items": [item.to_payload() for item in response_items],
            "provider_request_id": response_id,
            "continuation": build_chat_continuation_signal(
                {"finish_reason": finish_reason},
                {
                    "id": response_id,
                    "model": model_name or profile.model_name,
                },
                response_items,
            ).to_payload(),
        },
    )


def build_chat_continuation_signal(
    choice: dict[str, Any],
    payload: dict[str, Any],
    response_items: tuple[LlmResponseItem, ...],
) -> LlmContinuationSignal:
    finish_reason = (
        str(choice.get("finish_reason"))
        if choice.get("finish_reason") is not None
        else None
    )
    provider_payload = {
        key: value
        for key, value in {
            "response_id": payload.get("id"),
            "model": payload.get("model"),
            "finish_reason": finish_reason,
        }.items()
        if value is not None
    }
    has_tool_call = any(item.kind is LlmResponseItemKind.TOOL_CALL for item in response_items)
    if has_tool_call or finish_reason == "tool_calls":
        return LlmContinuationSignal(
            end_turn=False,
            needs_follow_up=True,
            reason=LlmContinuationReason.TOOL_CALL,
            provider_payload=provider_payload,
        )
    return LlmContinuationSignal(
        needs_follow_up=False,
        reason=LlmContinuationReason.NONE,
        provider_payload=provider_payload,
    )


def _first_chat_choice_and_message(
    profile: LlmProfile,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError(
            f"OpenAI-compatible profile '{profile.id}' returned no choices.",
        )
    choice = choices[0]
    if not isinstance(choice, dict):
        raise RuntimeError(
            f"OpenAI-compatible profile '{profile.id}' returned an invalid choice payload.",
        )
    message = choice.get("message")
    if not isinstance(message, dict):
        raise RuntimeError(
            f"OpenAI-compatible profile '{profile.id}' returned no message payload.",
        )
    return choice, message


def _usage_from_chat_payload(payload: dict[str, Any]) -> LlmUsage | None:
    usage_raw = payload.get("usage")
    if not isinstance(usage_raw, dict):
        return None
    return LlmUsage(
        input_tokens=usage_raw.get("prompt_tokens"),
        output_tokens=usage_raw.get("completion_tokens"),
        total_tokens=usage_raw.get("total_tokens"),
    )
