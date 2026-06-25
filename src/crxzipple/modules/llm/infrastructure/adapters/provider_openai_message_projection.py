from __future__ import annotations

from typing import Any

from crxzipple.modules.llm.domain import (
    LlmInputItem,
    LlmInputItemKind,
    LlmMessage,
)
from crxzipple.modules.llm.infrastructure.adapters.adapter_utils import (
    coerce_text_content,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_message_common import (
    assistant_function_call,
    base64_data_url,
    ensure_text_only_blocks,
    file_block_name,
    json_text,
    message_blocks,
    non_text_blocks,
    ref_block_text,
    tool_result,
)
from crxzipple.modules.llm.infrastructure.adapters.tool_schemas import (
    resolve_openai_tool_name,
)
from crxzipple.shared.content_blocks import extract_text_content


def openai_chat_messages(
    messages: tuple[LlmMessage, ...],
    *,
    tool_name_aliases: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for message in messages:
        tool_call = assistant_function_call(message)
        if tool_call is not None:
            tool_call_payload = {
                "id": tool_call["call_id"],
                "type": "function",
                "function": {
                    "name": resolve_openai_tool_name(
                        tool_call["name"],
                        tool_name_aliases=tool_name_aliases,
                    ),
                    "arguments": tool_call["arguments_text"],
                },
            }
            if payloads and payloads[-1].get("role") == "assistant":
                payloads[-1].setdefault("tool_calls", []).append(tool_call_payload)
                payloads[-1].setdefault("content", None)
            else:
                payloads.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [tool_call_payload],
                    },
                )
            continue

        tool_result_payload = tool_result(message)
        if tool_result_payload is not None:
            payloads.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_result_payload["call_id"],
                    "content": tool_result_payload["output_text"],
                },
            )
            attachment_payload = _openai_chat_tool_attachment_message(
                tool_result_payload,
            )
            if attachment_payload is not None:
                payloads.append(attachment_payload)
            continue

        payload: dict[str, Any] = {
            "role": message.role.value,
            "content": _openai_chat_message_content(message),
        }
        if message.name is not None:
            payload["name"] = message.name
        payloads.append(payload)
    return payloads


def openai_response_projected_input_items(
    input_items: tuple[LlmInputItem, ...],
    *,
    tool_name_aliases: dict[str, str] | None = None,
    continuation_delta_only: bool = False,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for item in input_items:
        payload = _openai_response_projected_input_item(
            item,
            tool_name_aliases=tool_name_aliases,
        )
        if payload is None:
            continue
        payloads.append(payload)
        if item.kind is LlmInputItemKind.FUNCTION_CALL_OUTPUT:
            attachment_payload = _openai_response_projected_tool_attachment_message(
                item,
            )
            if attachment_payload is not None:
                payloads.append(attachment_payload)
    if continuation_delta_only:
        delta_payloads = _openai_response_continuation_delta_items(payloads)
        if delta_payloads:
            return delta_payloads
    return payloads


def _openai_response_projected_input_item(
    item: LlmInputItem,
    *,
    tool_name_aliases: dict[str, str] | None,
) -> dict[str, Any] | None:
    payload = dict(item.payload)
    if item.kind is LlmInputItemKind.MESSAGE:
        role = str(payload.setdefault("role", "user"))
        if role == "system":
            return None
        payload["content"] = _openai_response_projected_message_content(
            payload.get("content", ""),
            role=role,
        )
        return payload
    if item.kind is LlmInputItemKind.FUNCTION_CALL:
        payload["type"] = "function_call"
        if "name" in payload:
            payload["name"] = resolve_openai_tool_name(
                str(payload["name"]),
                tool_name_aliases=tool_name_aliases,
            )
        if not isinstance(payload.get("arguments"), str):
            payload["arguments"] = json_text(payload.get("arguments"))
        return payload
    if item.kind is LlmInputItemKind.FUNCTION_CALL_OUTPUT:
        payload["type"] = "function_call_output"
        payload["output"] = coerce_text_content(payload.get("output"))
        payload.pop("name", None)
        payload.pop("tool_name", None)
        payload.pop("content_blocks", None)
        return payload
    if item.kind is LlmInputItemKind.REASONING:
        return _openai_response_reasoning_summary(payload)
    if item.kind is LlmInputItemKind.PROVIDER_ITEM:
        return payload
    return None


def _openai_response_projected_tool_attachment_message(
    item: LlmInputItem,
) -> dict[str, Any] | None:
    blocks = item.payload.get("content_blocks") or item.payload.get("output") or []
    if not isinstance(blocks, (list, tuple)):
        return None
    blocks = list(blocks)
    if not non_text_blocks(blocks):
        return None
    converted_blocks = [
        block for block in (_openai_response_part(block) for block in blocks) if block
    ]
    if not converted_blocks:
        return None
    return {
        "role": "user",
        "content": converted_blocks,
    }


def _openai_response_reasoning_summary(
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    text = payload.get("text")
    summary = payload.get("summary")
    if summary is None:
        text = text or extract_text_content(payload.get("content"))
    if summary is None and text is not None:
        summary = [{"type": "summary_text", "text": str(text)}]
    if not isinstance(summary, list) or not summary:
        return None
    return {
        "type": "reasoning",
        "summary": summary,
        **({"id": payload["id"]} if payload.get("id") else {}),
    }


def _openai_response_projected_message_content(value: Any, *, role: str) -> Any:
    if isinstance(value, list):
        return [
            _openai_response_projected_content_block(block, role=role)
            for block in value
        ]
    if role == "user":
        return [
            {
                "type": "input_text",
                "text": coerce_text_content(value),
            },
        ]
    if role == "assistant":
        return [
            {
                "type": "output_text",
                "text": coerce_text_content(value),
            },
        ]
    return value


def _openai_response_projected_content_block(
    block: Any,
    *,
    role: str,
) -> Any:
    if not isinstance(block, dict):
        return block
    block_type = block.get("type")
    if block_type == "text":
        return {
            **block,
            "type": "output_text" if role == "assistant" else "input_text",
        }
    if block_type == "image":
        return _openai_response_part(block)
    if block_type == "file":
        return _openai_response_part(block)
    return dict(block)


def _openai_response_continuation_delta_items(
    payloads: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    delta_items: list[dict[str, Any]] = []
    include_next_attachment = False
    for payload in payloads:
        if payload.get("type") == "function_call_output":
            delta_items.append(payload)
            include_next_attachment = True
            continue
        if include_next_attachment and payload.get("role") == "user":
            delta_items.append(payload)
            include_next_attachment = False
            continue
        include_next_attachment = False
    return delta_items


def _openai_chat_tool_attachment_message(
    tool_result_payload: dict[str, Any],
) -> dict[str, Any] | None:
    blocks = tool_result_payload.get("content_blocks") or []
    if not non_text_blocks(blocks):
        return None
    return {
        "role": "user",
        "content": [_openai_chat_part(block) for block in blocks],
    }


def _openai_chat_message_content(message: LlmMessage) -> Any:
    blocks = message_blocks(message)
    if not blocks:
        return coerce_text_content(message.content)
    if message.role.value == "user":
        return [_openai_chat_part(block) for block in blocks]
    ensure_text_only_blocks(blocks, provider_name="OpenAI chat")
    return extract_text_content(blocks) or ""


def _openai_chat_part(block: dict[str, Any]) -> dict[str, Any]:
    if block["type"] == "text":
        return {"type": "text", "text": block["text"]}
    if block["type"] in {"image_ref", "file_ref"}:
        return {"type": "text", "text": ref_block_text(block)}
    if block["type"] == "image":
        return {
            "type": "image_url",
            "image_url": {
                "url": base64_data_url(block["mime_type"], block["data"]),
            },
        }
    if block["type"] == "file":
        return {
            "type": "file",
            "file": {
                "file_data": block["data"],
                "filename": file_block_name(block),
            },
        }
    raise RuntimeError(f"OpenAI chat does not support '{block['type']}' content blocks yet.")


def _openai_response_part(block: dict[str, Any]) -> dict[str, Any]:
    if block["type"] == "text":
        return {"type": "input_text", "text": block["text"]}
    if block["type"] in {"image_ref", "file_ref"}:
        return {"type": "input_text", "text": ref_block_text(block)}
    if block["type"] == "image":
        return {
            "type": "input_image",
            "image_url": base64_data_url(block["mime_type"], block["data"]),
        }
    if block["type"] == "file":
        return {
            "type": "input_file",
            "file_data": block["data"],
            "filename": file_block_name(block),
        }
    raise RuntimeError(
        f"OpenAI Responses does not support '{block['type']}' content blocks yet.",
    )
