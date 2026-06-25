from __future__ import annotations

import json
from typing import Any

from crxzipple.modules.llm.domain import LlmMessage
from crxzipple.modules.llm.infrastructure.adapters.adapter_utils import (
    coerce_text_content,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_message_common import (
    assistant_function_call,
    ensure_text_only_blocks,
    message_blocks,
    non_text_blocks,
    ref_block_text,
    tool_result,
)


def gemini_contents(messages: tuple[LlmMessage, ...]) -> tuple[dict[str, Any], list[str]]:
    contents: list[dict[str, Any]] = []
    system_parts: list[str] = []
    for message in messages:
        if message.role.value == "system":
            system_parts.append(coerce_text_content(message.content))
            continue
        tool_call = assistant_function_call(message)
        if tool_call is not None:
            _append_gemini_model_part(
                contents,
                {
                    "functionCall": {
                        "id": tool_call["call_id"],
                        "name": tool_call["name"],
                        "args": tool_call["arguments_value"],
                    },
                },
            )
            continue
        tool_result_payload = tool_result(message)
        if tool_result_payload is not None:
            _append_gemini_tool_response_part(contents, tool_result_payload)
            continue
        role = "model" if message.role.value == "assistant" else "user"
        parts = _gemini_message_parts(message)
        if contents and contents[-1].get("role") == role:
            contents[-1].setdefault("parts", []).extend(parts)
        else:
            contents.append({"role": role, "parts": parts})
    return tuple(contents), system_parts


def _append_gemini_model_part(
    contents: list[dict[str, Any]],
    part: dict[str, Any],
) -> None:
    if contents and contents[-1].get("role") == "model":
        contents[-1].setdefault("parts", []).append(part)
        return
    contents.append({"role": "model", "parts": [part]})


def _append_gemini_tool_response_part(
    contents: list[dict[str, Any]],
    tool_result_payload: dict[str, Any],
) -> None:
    response_payload: dict[str, Any] = {
        "id": tool_result_payload["call_id"],
        "name": str(
            tool_result_payload["metadata"].get("tool_name")
            or tool_result_payload["call_id"],
        ),
        "response": {
            "result": _gemini_tool_result_value(tool_result_payload["output_text"]),
        },
    }
    parts = [{"functionResponse": response_payload}]
    parts.extend(_gemini_tool_attachment_parts(tool_result_payload))
    for part in parts:
        _append_gemini_user_part(contents, part)


def _append_gemini_user_part(
    contents: list[dict[str, Any]],
    part: dict[str, Any],
) -> None:
    if contents and contents[-1].get("role") == "user":
        contents[-1].setdefault("parts", []).append(part)
        return
    contents.append({"role": "user", "parts": [part]})


def _gemini_tool_result_value(output_text: str) -> Any:
    try:
        return json.loads(output_text)
    except json.JSONDecodeError:
        return output_text


def _gemini_tool_attachment_parts(
    tool_result_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    blocks = tool_result_payload.get("content_blocks") or []
    if not non_text_blocks(blocks):
        return []
    return [_gemini_part(block) for block in blocks]


def _gemini_message_parts(
    message: LlmMessage,
) -> list[dict[str, Any]]:
    role = "model" if message.role.value == "assistant" else "user"
    blocks = message_blocks(message)
    if not blocks:
        return [{"text": coerce_text_content(message.content)}]
    if role == "model":
        ensure_text_only_blocks(blocks, provider_name="Gemini model")
        return [{"text": block["text"]} for block in blocks if block.get("type") == "text"]
    return [_gemini_part(block) for block in blocks]


def _gemini_part(block: dict[str, Any]) -> dict[str, Any]:
    if block["type"] == "text":
        return {"text": block["text"]}
    if block["type"] in {"image_ref", "file_ref"}:
        return {"text": ref_block_text(block)}
    if block["type"] == "image":
        return {
            "inlineData": {
                "mimeType": block["mime_type"],
                "data": block["data"],
            },
        }
    if block["type"] == "file":
        return {
            "inlineData": {
                "mimeType": block["mime_type"],
                "data": block["data"],
            },
        }
    raise RuntimeError(f"Gemini does not support '{block['type']}' content blocks yet.")
