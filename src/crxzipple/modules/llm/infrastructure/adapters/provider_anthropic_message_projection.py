from __future__ import annotations

from typing import Any

from crxzipple.modules.llm.domain import LlmMessage
from crxzipple.modules.llm.infrastructure.adapters.adapter_utils import (
    coerce_text_content,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_message_common import (
    anthropic_supports_file_mime_type,
    anthropic_text_file_content,
    anthropic_treats_file_as_text,
    assistant_function_call,
    ensure_text_only_blocks,
    file_block_name,
    message_blocks,
    non_text_blocks,
    ref_block_text,
    tool_result,
)


def anthropic_messages(messages: tuple[LlmMessage, ...]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for message in messages:
        tool_call = assistant_function_call(message)
        if tool_call is not None:
            _append_anthropic_assistant_block(
                payloads,
                {
                    "type": "tool_use",
                    "id": tool_call["call_id"],
                    "name": tool_call["name"],
                    "input": tool_call["arguments_value"],
                },
            )
            continue
        tool_result_payload = tool_result(message)
        if tool_result_payload is not None:
            _append_anthropic_tool_result_block(payloads, tool_result_payload)
            continue
        payloads.append(
            {
                "role": (
                    "assistant" if message.role.value == "assistant" else "user"
                ),
                "content": _anthropic_message_content(message),
            },
        )
    return payloads


def _append_anthropic_assistant_block(
    payloads: list[dict[str, Any]],
    block: dict[str, Any],
) -> None:
    if payloads and payloads[-1].get("role") == "assistant":
        payloads[-1].setdefault("content", []).append(block)
        return
    payloads.append({"role": "assistant", "content": [block]})


def _append_anthropic_tool_result_block(
    payloads: list[dict[str, Any]],
    tool_result_payload: dict[str, Any],
) -> None:
    content: str | list[dict[str, Any]] = tool_result_payload["output_text"]
    attachment_blocks = _anthropic_tool_attachment_message(tool_result_payload)
    if attachment_blocks:
        content = [
            {"type": "text", "text": tool_result_payload["output_text"]},
            *attachment_blocks,
        ]
    block = {
        "type": "tool_result",
        "tool_use_id": tool_result_payload["call_id"],
        "content": content,
    }
    if payloads and payloads[-1].get("role") == "user":
        payloads[-1].setdefault("content", []).append(block)
        return
    payloads.append({"role": "user", "content": [block]})


def _anthropic_tool_attachment_message(
    tool_result_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    blocks = tool_result_payload.get("content_blocks") or []
    if not non_text_blocks(blocks):
        return []
    return [_anthropic_part(block) for block in blocks]


def _anthropic_message_content(
    message: LlmMessage,
) -> list[dict[str, Any]]:
    role = "assistant" if message.role.value == "assistant" else "user"
    blocks = message_blocks(message)
    if not blocks:
        return [{"type": "text", "text": coerce_text_content(message.content)}]
    if role == "assistant":
        ensure_text_only_blocks(blocks, provider_name="Anthropic assistant")
        return [
            {"type": "text", "text": block["text"]}
            for block in blocks
            if block.get("type") == "text"
        ]
    return [_anthropic_part(block) for block in blocks]


def _anthropic_part(block: dict[str, Any]) -> dict[str, Any]:
    if block["type"] == "text":
        return {"type": "text", "text": block["text"]}
    if block["type"] in {"image_ref", "file_ref"}:
        return {"type": "text", "text": ref_block_text(block)}
    if block["type"] == "image":
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": block["mime_type"],
                "data": block["data"],
            },
        }
    if block["type"] == "file":
        if anthropic_treats_file_as_text(str(block["mime_type"])):
            return {
                "type": "text",
                "text": anthropic_text_file_content(block),
            }
        if not anthropic_supports_file_mime_type(str(block["mime_type"])):
            raise RuntimeError(
                "Anthropic only supports PDF and text-like file content blocks right now.",
            )
        return {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": block["mime_type"],
                "data": block["data"],
            },
            "title": file_block_name(block),
        }
    raise RuntimeError(
        f"Anthropic does not support '{block['type']}' content blocks yet.",
    )
