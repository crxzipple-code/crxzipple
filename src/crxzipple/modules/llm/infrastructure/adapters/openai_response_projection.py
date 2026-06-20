from __future__ import annotations

from typing import Any

from crxzipple.modules.llm.application.streaming import LlmStreamEvent
from crxzipple.modules.llm.domain.value_objects import (
    LlmContinuationReason,
    LlmContinuationSignal,
    LlmMessagePhase,
    LlmMessageRole,
    LlmResponseItem,
    LlmResponseItemKind,
    ToolCallIntent,
    utcnow,
)

from .adapter_utils import parse_json_arguments


def build_tool_call_intents(
    tool_calls: list[dict[str, Any]],
    *,
    tool_name_aliases: dict[str, str] | None = None,
) -> tuple[ToolCallIntent, ...]:
    return tuple(
        ToolCallIntent(
            id=str(item.get("id") or item.get("call_id") or item.get("name") or "tool_call"),
            name=(
                tool_name_aliases.get(str(item.get("name") or ""), str(item.get("name") or ""))
                if tool_name_aliases is not None
                else str(item.get("name") or "")
            ),
            arguments=parse_json_arguments(item.get("arguments") or item.get("input")),
        )
        for item in tool_calls
        if item.get("name")
    )


def build_openai_response_items(
    *,
    invocation_id: str,
    response_payload: dict[str, Any],
    tool_name_aliases: dict[str, str] | None = None,
) -> tuple[LlmResponseItem, ...]:
    output = response_payload.get("output")
    if not isinstance(output, list):
        return ()

    items: list[LlmResponseItem] = []
    for index, raw_item in enumerate(output, start=1):
        if not isinstance(raw_item, dict):
            continue
        item_type = str(raw_item.get("type") or "unknown")
        kind = _openai_response_item_kind(item_type)
        content_payload = _openai_response_item_content_payload(
            raw_item,
            item_type=item_type,
            tool_name_aliases=tool_name_aliases,
        )
        tool_name = content_payload.get("tool_name")
        call_id = raw_item.get("call_id") or raw_item.get("id")
        provider_item_id = raw_item.get("id") or raw_item.get("call_id") or index
        now = utcnow()
        items.append(
            LlmResponseItem(
                id=f"{invocation_id}:item:{index}",
                invocation_id=invocation_id,
                sequence_no=index,
                kind=kind,
                role=(
                    LlmMessageRole.ASSISTANT
                    if kind
                    in {
                        LlmResponseItemKind.ASSISTANT_MESSAGE,
                        LlmResponseItemKind.REASONING,
                        LlmResponseItemKind.TOOL_CALL,
                        LlmResponseItemKind.PROVIDER_EXTERNAL_ITEM,
                    }
                    else None
                ),
                phase=(
                    _openai_message_phase(raw_item)
                    if kind is LlmResponseItemKind.ASSISTANT_MESSAGE
                    else LlmMessagePhase.UNKNOWN
                ),
                content_payload=content_payload,
                provider_payload=dict(raw_item),
                provider_item_id=str(provider_item_id),
                provider_item_type=item_type,
                call_id=str(call_id) if call_id is not None else None,
                tool_name=str(tool_name) if tool_name is not None else None,
                provider_replay_candidate=True,
                user_timeline_candidate=_openai_response_item_user_timeline_default(kind),
                created_at=now,
                completed_at=now,
            ),
        )
    return tuple(items)


def build_openai_continuation_signal(
    response_payload: dict[str, Any],
    response_items: tuple[LlmResponseItem, ...],
) -> LlmContinuationSignal:
    raw_end_turn = response_payload.get("end_turn")
    end_turn = bool(raw_end_turn) if isinstance(raw_end_turn, bool) else None
    has_tool_call = any(item.kind is LlmResponseItemKind.TOOL_CALL for item in response_items)
    if has_tool_call:
        return LlmContinuationSignal(
            end_turn=end_turn,
            needs_follow_up=True,
            reason=LlmContinuationReason.TOOL_CALL,
            provider_payload=_openai_continuation_payload(response_payload),
        )
    if end_turn is False:
        return LlmContinuationSignal(
            end_turn=False,
            needs_follow_up=True,
            reason=LlmContinuationReason.PROVIDER_END_TURN_FALSE,
            provider_payload=_openai_continuation_payload(response_payload),
        )
    return LlmContinuationSignal(
        end_turn=end_turn,
        needs_follow_up=False,
        reason=LlmContinuationReason.NONE,
        provider_payload=_openai_continuation_payload(response_payload),
    )


def openai_response_stream_event(
    *,
    event_name: str,
    payload: dict[str, Any],
    sequence: int,
) -> LlmStreamEvent | None:
    if event_name in {"response.output_item.added", "response.output_item.created"}:
        item = payload.get("item")
        item_id = _openai_stream_item_id(payload, item)
        return LlmStreamEvent(
            type="item_started",
            sequence=sequence,
            data={
                "item_id": item_id,
                "provider_event_type": event_name,
                "provider_payload": dict(payload),
            },
        )
    if event_name == "response.output_item.done":
        item = payload.get("item")
        item_id = _openai_stream_item_id(payload, item)
        return LlmStreamEvent(
            type="item_completed",
            sequence=sequence,
            data={
                "item_id": item_id,
                "provider_event_type": event_name,
                "provider_payload": dict(payload),
            },
        )
    if event_name in {
        "response.reasoning_summary_text.delta",
        "response.reasoning_summary.delta",
    }:
        delta = payload.get("delta")
        return LlmStreamEvent(
            type="reasoning_summary_delta",
            sequence=sequence,
            data={
                "item_id": str(payload.get("item_id") or payload.get("output_item_id") or ""),
                "text": str(delta) if delta is not None else "",
                "provider_event_type": event_name,
                "provider_payload": dict(payload),
            },
        )
    if event_name in {"response.reasoning_text.delta", "response.reasoning.delta"}:
        delta = payload.get("delta")
        return LlmStreamEvent(
            type="reasoning_raw_delta",
            sequence=sequence,
            data={
                "item_id": str(payload.get("item_id") or payload.get("output_item_id") or ""),
                "text": str(delta) if delta is not None else "",
                "provider_event_type": event_name,
                "provider_payload": dict(payload),
            },
        )
    if event_name in {
        "response.function_call_arguments.delta",
        "response.tool_call_arguments.delta",
    }:
        delta = payload.get("delta")
        return LlmStreamEvent(
            type="tool_argument_delta",
            sequence=sequence,
            data={
                "item_id": str(payload.get("item_id") or payload.get("output_item_id") or ""),
                "delta": str(delta) if delta is not None else "",
                "provider_event_type": event_name,
                "provider_payload": dict(payload),
            },
        )
    return None


def _openai_message_phase(item: dict[str, Any]) -> LlmMessagePhase:
    raw_phase = item.get("phase")
    if raw_phase is None:
        return LlmMessagePhase.UNKNOWN
    try:
        return LlmMessagePhase(str(raw_phase))
    except ValueError:
        return LlmMessagePhase.UNKNOWN


def _openai_response_item_user_timeline_default(kind: LlmResponseItemKind) -> bool:
    return kind is LlmResponseItemKind.ASSISTANT_MESSAGE


def _openai_stream_item_id(payload: dict[str, Any], item: Any) -> str:
    if isinstance(item, dict):
        item_id = item.get("id") or item.get("call_id")
        if item_id is not None:
            return str(item_id)
    item_id = payload.get("item_id") or payload.get("output_item_id")
    if item_id is not None:
        return str(item_id)
    output_index = payload.get("output_index")
    if output_index is not None:
        return f"output:{output_index}"
    return ""


def _openai_response_item_kind(item_type: str) -> LlmResponseItemKind:
    if item_type == "message":
        return LlmResponseItemKind.ASSISTANT_MESSAGE
    if item_type == "reasoning":
        return LlmResponseItemKind.REASONING
    if item_type in {"function_call", "custom_tool_call"}:
        return LlmResponseItemKind.TOOL_CALL
    if item_type == "function_call_output":
        return LlmResponseItemKind.TOOL_RESULT
    if item_type in {"web_search_call", "image_generation_call", "file_search_call"}:
        return LlmResponseItemKind.PROVIDER_EXTERNAL_ITEM
    return LlmResponseItemKind.UNKNOWN


def _openai_response_item_content_payload(
    item: dict[str, Any],
    *,
    item_type: str,
    tool_name_aliases: dict[str, str] | None,
) -> dict[str, Any]:
    if item_type == "message":
        return {
            "text": _openai_message_item_text(item),
            "content": item.get("content") if isinstance(item.get("content"), list) else [],
        }
    if item_type == "reasoning":
        return {
            "summary": item.get("summary") if isinstance(item.get("summary"), list) else [],
            "text": _openai_reasoning_item_text(item),
        }
    if item_type in {"function_call", "custom_tool_call"}:
        raw_name = str(item.get("name") or "")
        return {
            "call_id": item.get("call_id") or item.get("id"),
            "tool_name": (
                tool_name_aliases.get(raw_name, raw_name)
                if tool_name_aliases is not None
                else raw_name
            ),
            "arguments": parse_json_arguments(item.get("arguments") or item.get("input")),
        }
    if item_type == "function_call_output":
        return {
            "call_id": item.get("call_id") or item.get("id"),
            "output": item.get("output"),
        }
    return dict(item)


def _openai_message_item_text(item: dict[str, Any]) -> str | None:
    fragments: list[str] = []
    content = item.get("content")
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") in {"output_text", "text"} and block.get("text") is not None:
                fragments.append(str(block.get("text")))
    return "".join(fragments) or None


def _openai_reasoning_item_text(item: dict[str, Any]) -> str | None:
    text = item.get("text")
    if text is not None:
        return str(text)
    summary = item.get("summary")
    fragments: list[str] = []
    if isinstance(summary, list):
        for block in summary:
            if isinstance(block, dict) and block.get("text") is not None:
                fragments.append(str(block.get("text")))
    return "".join(fragments) or None


def _openai_continuation_payload(response_payload: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in ("id", "status", "end_turn", "model"):
        if key in response_payload:
            payload[key] = response_payload[key]
    return payload
