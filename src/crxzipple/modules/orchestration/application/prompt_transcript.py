from __future__ import annotations

import json
from dataclasses import dataclass, replace

from crxzipple.modules.llm.domain import LlmMessage, LlmMessageRole
from crxzipple.modules.orchestration.application.prompting import estimate_text_tokens
from crxzipple.modules.session.domain import SessionMessage
from crxzipple.shared.content_blocks import (
    content_blocks_from_payload,
    describe_content_for_text_fallback,
    extract_text_content,
    text_content_block,
)


@dataclass(frozen=True, slots=True)
class PromptTranscript:
    messages: tuple[LlmMessage, ...]
    message_count: int
    chars: int
    estimated_tokens: int


def build_prompt_transcript(
    messages: tuple[SessionMessage, ...],
    *,
    max_chars: int | None = None,
) -> PromptTranscript:
    filtered_messages = _prune_processed_history_attachments(
        _filter_transcript_messages(messages),
    )
    filtered_messages = _truncate_messages_to_recent_budget(
        filtered_messages,
        max_chars=max_chars,
    )
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
    if role is LlmMessageRole.TOOL and "status" in message.content_payload:
        metadata["tool_status"] = message.content_payload["status"]
    if role is LlmMessageRole.TOOL and "error" in message.content_payload:
        metadata["tool_error"] = message.content_payload["error"]
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
    if (
        role is LlmMessageRole.ASSISTANT
        and message.content_payload.get("type") == "function_call"
    ):
        return dict(message.content_payload)
    if role is LlmMessageRole.TOOL:
        blocks = content_blocks_from_payload(message.content_payload)
        if blocks:
            return blocks
        if "error" in message.content_payload:
            return [text_content_block(describe_content_for_text_fallback(message.content_payload["error"]))]
        return [text_content_block("Tool completed.")]
    blocks = content_blocks_from_payload(message.content_payload)
    if blocks:
        return blocks
    return [
        text_content_block(
            json.dumps(
                message.content_payload,
                ensure_ascii=True,
                sort_keys=True,
            ),
        ),
    ]


def _message_content_chars(content: object) -> int:
    text_content = extract_text_content(content)
    if text_content is not None:
        return len(text_content)
    return len(describe_content_for_text_fallback(content))


def _message_content_tokens(content: object) -> int:
    text_content = extract_text_content(content)
    if text_content is not None:
        return estimate_text_tokens(text_content)
    return estimate_text_tokens(describe_content_for_text_fallback(content))


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


def _prune_processed_history_attachments(
    messages: tuple[SessionMessage, ...],
) -> tuple[SessionMessage, ...]:
    last_assistant_index = max(
        (
            index
            for index, message in enumerate(messages)
            if message.role == "assistant"
        ),
        default=-1,
    )
    if last_assistant_index <= 0:
        return messages

    pruned: list[SessionMessage] = []
    for index, message in enumerate(messages):
        if index >= last_assistant_index:
            pruned.append(message)
            continue
        blocks = content_blocks_from_payload(message.content_payload)
        if not blocks or all(block.get("type") == "text" for block in blocks):
            pruned.append(message)
            continue
        replacement_blocks = []
        for block in blocks:
            block_type = str(block.get("type") or "").strip()
            if block_type == "text":
                replacement_blocks.append(block)
                continue
            placeholder = "[attachment data removed - already processed by model]"
            if block_type in {"image", "image_ref"}:
                placeholder = "[image data removed - already processed by model]"
            elif block_type in {"file", "file_ref"}:
                placeholder = "[file data removed - already processed by model]"
            replacement_blocks.append(text_content_block(placeholder))
        payload = dict(message.content_payload)
        payload["blocks"] = replacement_blocks
        replacement_text = extract_text_content({"blocks": replacement_blocks})
        if replacement_text is not None:
            payload["text"] = replacement_text
        else:
            payload.pop("text", None)
        pruned.append(replace(message, content_payload=payload))
    return tuple(pruned)


def _truncate_messages_to_recent_budget(
    messages: tuple[SessionMessage, ...],
    *,
    max_chars: int | None,
) -> tuple[SessionMessage, ...]:
    if max_chars is None or max_chars <= 0:
        return messages

    assistant_function_call_indices: dict[str, int] = {}
    for index, message in enumerate(messages):
        if message.role != "assistant":
            continue
        if message.content_payload.get("type") != "function_call":
            continue
        tool_call_id = message.metadata.get("tool_call_id")
        if isinstance(tool_call_id, str) and tool_call_id.strip():
            assistant_function_call_indices[tool_call_id.strip()] = index

    kept: list[tuple[int, SessionMessage]] = []
    kept_indices: set[int] = set()
    required_indices: set[int] = set()
    remaining_chars = max_chars
    cutoff_reached = False

    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        forced = index in required_indices
        if not forced and cutoff_reached:
            continue

        message_chars = _session_message_content_chars(message)
        if not forced and kept and message_chars > remaining_chars:
            cutoff_reached = True
            continue
        if (
            not forced
            and not kept
            and remaining_chars > 0
            and message_chars > remaining_chars
        ):
            message = _truncate_message_to_recent_chars(message, remaining_chars)
            message_chars = _session_message_content_chars(message)
            cutoff_reached = True

        kept.append((index, message))
        kept_indices.add(index)
        remaining_chars = max(0, remaining_chars - message_chars)

        if message.role != "tool":
            continue
        tool_call_id = message.metadata.get("tool_call_id")
        if not isinstance(tool_call_id, str) or not tool_call_id.strip():
            continue
        function_call_index = assistant_function_call_indices.get(tool_call_id.strip())
        if function_call_index is not None and function_call_index not in kept_indices:
            required_indices.add(function_call_index)

    if len(kept) == len(messages):
        return messages
    kept.sort(key=lambda item: item[0])
    return tuple(message for _, message in kept)


def _session_message_content_chars(message: SessionMessage) -> int:
    try:
        role = LlmMessageRole(message.role)
    except ValueError:
        role = LlmMessageRole.USER
    return _message_content_chars(_extract_content(message, role=role))


def _truncate_message_to_recent_chars(
    message: SessionMessage,
    max_chars: int,
) -> SessionMessage:
    if max_chars <= 0:
        return message
    if message.role == "assistant" and message.content_payload.get("type") == "function_call":
        return message
    blocks = content_blocks_from_payload(message.content_payload)
    text_content = extract_text_content(blocks if blocks else message.content_payload)
    if text_content is None:
        fallback_text = describe_content_for_text_fallback(message.content_payload)
        truncated_text = fallback_text[-max_chars:]
        return replace(
            message,
            content_payload={
                "blocks": [text_content_block(truncated_text)],
                "text": truncated_text,
            },
        )
    truncated_text = text_content[-max_chars:]
    payload = dict(message.content_payload)
    payload["blocks"] = [text_content_block(truncated_text)]
    payload["text"] = truncated_text
    return replace(message, content_payload=payload)
