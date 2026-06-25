from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from crxzipple.modules.llm.domain import (
    LlmMessagePhase,
    LlmMessageRole,
    LlmResponseItem,
    LlmResponseItemKind,
    utcnow,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_response_projection import (
    build_tool_call_intents,
)

TOOL_CALL_BLOCK_PATTERN = re.compile(
    r"<tool_call>\s*(.*?)\s*</tool_call>",
    re.DOTALL,
)
FUNCTION_PATTERN = re.compile(
    r"<function=([^>]+)>\s*(.*?)\s*</function>",
    re.DOTALL,
)
PARAMETER_PATTERN = re.compile(
    r"<parameter=([^>]+)>\s*(.*?)\s*</parameter>",
    re.DOTALL,
)


def chat_message_tool_calls_and_text(
    message: dict[str, Any],
) -> tuple[list[dict[str, Any]], str | None]:
    raw_tool_calls: list[dict[str, Any]] = []
    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list):
        for item in tool_calls:
            if not isinstance(item, dict):
                continue
            function_payload = item.get("function")
            raw_tool_calls.append(
                {
                    "id": item.get("id"),
                    "name": (
                        function_payload.get("name")
                        if isinstance(function_payload, dict)
                        else None
                    ),
                    "arguments": (
                        function_payload.get("arguments")
                        if isinstance(function_payload, dict)
                        else None
                    ),
                },
            )
    content_text = (
        str(message.get("content")) if message.get("content") is not None else None
    )
    if not raw_tool_calls and content_text:
        parsed_tool_calls = parse_xmlish_tool_calls(content_text)
        if parsed_tool_calls:
            raw_tool_calls.extend(parsed_tool_calls)
            content_text = strip_xmlish_tool_calls(content_text)
    return raw_tool_calls, content_text


def parse_xmlish_tool_calls(content: str) -> list[dict[str, Any]]:
    tool_calls: list[dict[str, Any]] = []
    for block_match in TOOL_CALL_BLOCK_PATTERN.finditer(content):
        block_body = block_match.group(1)
        function_match = FUNCTION_PATTERN.search(block_body)
        if function_match is None:
            continue
        function_name = function_match.group(1).strip()
        parameter_body = function_match.group(2)
        arguments: dict[str, Any] = {}
        for parameter_match in PARAMETER_PATTERN.finditer(parameter_body):
            parameter_name = parameter_match.group(1).strip()
            parameter_value = parameter_match.group(2).strip()
            if parameter_name:
                arguments[parameter_name] = parameter_value
        if not function_name:
            continue
        tool_calls.append(
            {
                "id": f"chatcmpl-tool-{uuid4().hex}",
                "name": function_name,
                "arguments": arguments,
            },
        )
    return tool_calls


def strip_xmlish_tool_calls(content: str) -> str | None:
    stripped = TOOL_CALL_BLOCK_PATTERN.sub("", content).strip()
    return stripped or None


def build_chat_response_items(
    *,
    invocation_id: str,
    content_text: str | None,
    raw_tool_calls: list[dict[str, Any]],
    provider_response_id: str | None,
    model_name: str | None,
    transport: str,
    tool_name_aliases: dict[str, str] | None,
) -> tuple[LlmResponseItem, ...]:
    items: list[LlmResponseItem] = []
    now = utcnow()
    if content_text is not None:
        sequence_no = len(items) + 1
        provider_item_id = (
            f"{provider_response_id}:message"
            if provider_response_id is not None
            else f"{invocation_id}:message:{sequence_no}"
        )
        items.append(
            LlmResponseItem(
                id=f"{invocation_id}:item:{sequence_no}",
                invocation_id=invocation_id,
                sequence_no=sequence_no,
                kind=LlmResponseItemKind.ASSISTANT_MESSAGE,
                role=LlmMessageRole.ASSISTANT,
                phase=LlmMessagePhase.FINAL_ANSWER,
                content_payload={"text": content_text},
                provider_payload={
                    "type": "chat.completion.message",
                    "response_id": provider_response_id,
                    "model": model_name,
                    "transport": transport,
                },
                provider_item_id=provider_item_id,
                provider_item_type="chat.completion.message",
                provider_replay_candidate=True,
                user_timeline_candidate=True,
                created_at=now,
                completed_at=now,
            ),
        )
    for tool_call in build_tool_call_intents(
        raw_tool_calls,
        tool_name_aliases=tool_name_aliases,
    ):
        sequence_no = len(items) + 1
        items.append(
            LlmResponseItem(
                id=f"{invocation_id}:item:{sequence_no}",
                invocation_id=invocation_id,
                sequence_no=sequence_no,
                kind=LlmResponseItemKind.TOOL_CALL,
                role=LlmMessageRole.ASSISTANT,
                phase=LlmMessagePhase.UNKNOWN,
                content_payload={
                    "call_id": tool_call.id,
                    "tool_name": tool_call.name,
                    "arguments": dict(tool_call.arguments),
                },
                provider_payload={
                    "type": "chat.completion.tool_call",
                    "response_id": provider_response_id,
                    "model": model_name,
                    "transport": transport,
                },
                provider_item_id=tool_call.id,
                provider_item_type="chat.completion.tool_call",
                call_id=tool_call.id,
                tool_name=tool_call.name,
                provider_replay_candidate=True,
                user_timeline_candidate=False,
                created_at=now,
                completed_at=now,
            ),
        )
    return tuple(items)
