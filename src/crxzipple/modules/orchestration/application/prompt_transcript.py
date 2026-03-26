from __future__ import annotations

import json
from dataclasses import dataclass

from crxzipple.modules.llm.domain import LlmMessage, LlmMessageRole
from crxzipple.modules.orchestration.application.prompting import estimate_text_tokens
from crxzipple.modules.session.domain import SessionMessage


@dataclass(frozen=True, slots=True)
class PromptTranscript:
    messages: tuple[LlmMessage, ...]
    message_count: int
    chars: int
    estimated_tokens: int


def build_prompt_transcript(
    messages: tuple[SessionMessage, ...],
) -> PromptTranscript:
    filtered_messages = _filter_transcript_messages(messages)
    llm_messages = tuple(_to_llm_message(message) for message in filtered_messages)
    return PromptTranscript(
        messages=llm_messages,
        message_count=len(llm_messages),
        chars=sum(_message_content_chars(message.content) for message in llm_messages),
        estimated_tokens=sum(
            _message_content_tokens(message.content)
            for message in llm_messages
        ),
    )


def _to_llm_message(message: SessionMessage) -> LlmMessage:
    try:
        role = LlmMessageRole(message.role)
    except ValueError:
        role = LlmMessageRole.USER
    tool_call_id = message.metadata.get("tool_call_id")
    if not isinstance(tool_call_id, str) or not tool_call_id.strip():
        tool_call_id = None
    tool_name = message.metadata.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name.strip():
        payload_tool_name = message.content_payload.get("tool_name")
        if isinstance(payload_tool_name, str) and payload_tool_name.strip():
            tool_name = payload_tool_name.strip()
        else:
            tool_name = None
    metadata = {
        "session_message_id": message.id,
        "kind": message.kind.value,
        "source_kind": message.source_kind,
        "source_id": message.source_id,
    }
    if tool_name is not None:
        metadata["tool_name"] = tool_name
    return LlmMessage(
        role=role,
        content=_extract_content(message, role=role),
        name=tool_name,
        tool_call_id=tool_call_id,
        metadata=metadata,
    )


def _extract_content(
    message: SessionMessage,
    *,
    role: LlmMessageRole,
) -> object:
    if message.content is not None and message.content.strip():
        return message.content
    if (
        role is LlmMessageRole.ASSISTANT
        and message.content_payload.get("type") == "function_call"
    ):
        return dict(message.content_payload)
    text_content = message.content_payload.get("text")
    if isinstance(text_content, str) and text_content.strip():
        return text_content
    return json.dumps(
        message.content_payload,
        ensure_ascii=True,
        sort_keys=True,
    )


def _message_content_chars(content: object) -> int:
    if isinstance(content, str):
        return len(content)
    return len(
        json.dumps(
            content,
            ensure_ascii=True,
            sort_keys=True,
        ),
    )


def _message_content_tokens(content: object) -> int:
    if isinstance(content, str):
        return estimate_text_tokens(content)
    return estimate_text_tokens(
        json.dumps(
            content,
            ensure_ascii=True,
            sort_keys=True,
        ),
    )


def _filter_transcript_messages(
    messages: tuple[SessionMessage, ...],
) -> tuple[SessionMessage, ...]:
    completed_tool_call_ids = {
        tool_call_id.strip()
        for message in messages
        if message.role == "tool"
        for tool_call_id in (message.metadata.get("tool_call_id"),)
        if isinstance(tool_call_id, str) and tool_call_id.strip()
    }
    filtered: list[SessionMessage] = []
    for message in messages:
        is_function_call = (
            message.role == "assistant"
            and message.content_payload.get("type") == "function_call"
        )
        if not is_function_call:
            filtered.append(message)
            continue
        tool_call_id = message.metadata.get("tool_call_id")
        if (
            isinstance(tool_call_id, str)
            and tool_call_id.strip()
            and tool_call_id.strip() in completed_tool_call_ids
        ):
            filtered.append(message)
    return tuple(filtered)
