from __future__ import annotations

import base64
import json
from typing import Any

from crxzipple.modules.llm.domain.value_objects import (
    LlmInputItem,
    LlmInputItemKind,
    LlmMessage,
)
from crxzipple.modules.llm.infrastructure.adapters.adapter_utils import (
    coerce_text_content,
    parse_json_arguments,
)
from crxzipple.modules.llm.infrastructure.adapters.tool_schemas import (
    resolve_openai_tool_name,
)
from crxzipple.modules.llm.infrastructure.rendering.input_projection import (
    messages_from_projected_input_items as messages_from_projected_input_items,
    provider_context_messages as provider_context_messages,
)
from crxzipple.shared.content_blocks import (
    describe_content_for_text_fallback,
    extract_text_content,
    normalize_content_blocks,
)


def openai_chat_messages(
    messages: tuple[LlmMessage, ...],
    *,
    tool_name_aliases: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for message in messages:
        tool_call = _assistant_function_call(message)
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

        tool_result = _tool_result(message)
        if tool_result is not None:
            payloads.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_result["call_id"],
                    "content": tool_result["output_text"],
                },
            )
            attachment_payload = _openai_chat_tool_attachment_message(tool_result)
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


def projected_input_items_from_messages(
    messages: tuple[LlmMessage, ...],
    *,
    source: str = "adapter_request_message",
) -> tuple[LlmInputItem, ...]:
    input_items: list[LlmInputItem] = []
    for message in messages:
        metadata = dict(message.metadata)
        tool_call = _assistant_function_call(message)
        if tool_call is not None:
            input_items.append(
                LlmInputItem(
                    kind=LlmInputItemKind.FUNCTION_CALL,
                    payload={
                        "type": "function_call",
                        "call_id": tool_call["call_id"],
                        "name": tool_call["name"],
                        "arguments": tool_call["arguments_value"],
                    },
                    source=source,
                    metadata=metadata,
                ),
            )
            continue
        tool_result = _tool_result(message)
        if tool_result is not None:
            tool_name = message.name or message.metadata.get("tool_name")
            if isinstance(tool_name, str) and tool_name.strip():
                metadata.setdefault("tool_name", tool_name.strip())
            input_items.append(
                LlmInputItem(
                    kind=LlmInputItemKind.FUNCTION_CALL_OUTPUT,
                    payload={
                        "type": "function_call_output",
                        "call_id": tool_result["call_id"],
                        "output": tool_result["content_blocks"],
                        **(
                            {"name": tool_name.strip()}
                            if isinstance(tool_name, str) and tool_name.strip()
                            else {}
                        ),
                    },
                    source=source,
                    metadata=metadata,
                ),
            )
            continue
        input_items.append(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={
                    "role": message.role.value,
                    "content": message.content,
                    **({"name": message.name} if message.name is not None else {}),
                },
                source=source,
                metadata=metadata,
            ),
        )
    return tuple(input_items)


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
            payload["arguments"] = _json_text(payload.get("arguments"))
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
    if not _non_text_blocks(blocks):
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


def _json_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value if value is not None else {}, ensure_ascii=True, sort_keys=True)


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


def anthropic_messages(messages: tuple[LlmMessage, ...]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for message in messages:
        tool_call = _assistant_function_call(message)
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
        tool_result = _tool_result(message)
        if tool_result is not None:
            _append_anthropic_tool_result_block(payloads, tool_result)
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


def _assistant_function_call(message: LlmMessage) -> dict[str, Any] | None:
    if message.role.value != "assistant":
        return None
    content = message.content if isinstance(message.content, dict) else {}
    content_type = str(content.get("type") or "")
    content_name = content.get("name") if content_type == "function_call" else None
    content_call_id = (
        content.get("call_id") or content.get("id")
        if content_type == "function_call"
        else None
    )
    call_id = message.tool_call_id or content_call_id
    name = message.name or content_name
    if not isinstance(call_id, str) or not call_id.strip():
        return None
    if not isinstance(name, str) or not name.strip():
        return None
    arguments = getattr(message, "function_arguments", None)
    if arguments is None:
        arguments = content.get("arguments") if content_type == "function_call" else None
    if arguments is None:
        arguments = content.get("input") if content_type == "function_call" else None
    if arguments is None:
        arguments = message.metadata.get("arguments")
    arguments_text = _json_text(arguments)
    return {
        "call_id": call_id.strip(),
        "name": name.strip(),
        "arguments_text": arguments_text,
        "arguments_value": parse_json_arguments(arguments),
    }


def _tool_result(message: LlmMessage) -> dict[str, Any] | None:
    if not message.tool_call_id or message.role.value != "tool":
        return None
    blocks = _message_blocks(message)
    output_text = describe_content_for_text_fallback(blocks)
    if not output_text.strip():
        output_text = "Tool completed."
    return {
        "call_id": message.tool_call_id,
        "output_text": output_text,
        "content_blocks": blocks,
        "metadata": dict(message.metadata),
    }


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
    tool_result: dict[str, Any],
) -> None:
    content: str | list[dict[str, Any]] = tool_result["output_text"]
    attachment_blocks = _anthropic_tool_attachment_message(tool_result)
    if attachment_blocks:
        content = [
            {"type": "text", "text": tool_result["output_text"]},
            *attachment_blocks,
        ]
    block = {
        "type": "tool_result",
        "tool_use_id": tool_result["call_id"],
        "content": content,
    }
    if payloads and payloads[-1].get("role") == "user":
        payloads[-1].setdefault("content", []).append(block)
        return
    payloads.append({"role": "user", "content": [block]})


def gemini_contents(messages: tuple[LlmMessage, ...]) -> tuple[dict[str, Any], list[str]]:
    contents: list[dict[str, Any]] = []
    system_parts: list[str] = []
    for message in messages:
        if message.role.value == "system":
            system_parts.append(coerce_text_content(message.content))
            continue
        tool_call = _assistant_function_call(message)
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
        tool_result = _tool_result(message)
        if tool_result is not None:
            _append_gemini_tool_response_part(contents, tool_result)
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


def _append_gemini_user_text_part(
    contents: list[dict[str, Any]],
    text: str,
) -> None:
    if contents and contents[-1].get("role") == "user":
        contents[-1].setdefault("parts", []).append({"text": text})
        return
    contents.append({"role": "user", "parts": [{"text": text}]})


def _append_gemini_tool_response_part(
    contents: list[dict[str, Any]],
    tool_result: dict[str, Any],
) -> None:
    response_payload: dict[str, Any] = {
        "id": tool_result["call_id"],
        "name": str(tool_result["metadata"].get("tool_name") or tool_result["call_id"]),
        "response": {"result": _gemini_tool_result_value(tool_result["output_text"])},
    }
    parts = [{"functionResponse": response_payload}]
    parts.extend(_gemini_tool_attachment_parts(tool_result))
    for part in parts:
        _append_gemini_user_part(contents, part)


def _append_gemini_user_part(contents: list[dict[str, Any]], part: dict[str, Any]) -> None:
    if contents and contents[-1].get("role") == "user":
        contents[-1].setdefault("parts", []).append(part)
        return
    contents.append({"role": "user", "parts": [part]})


def _coerce_json_like_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {
            str(key): _coerce_json_like_value(item)
            for key, item in value.items()
            if item is not None
        }
    if isinstance(value, (list, tuple)):
        return [_coerce_json_like_value(item) for item in value]
    return str(value)


def _gemini_tool_result_value(output_text: str) -> Any:
    try:
        return json.loads(output_text)
    except json.JSONDecodeError:
        return output_text


def _non_text_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [block for block in blocks if block.get("type") not in {"text"}]


def _openai_chat_tool_attachment_message(
    tool_result: dict[str, Any],
) -> dict[str, Any] | None:
    blocks = tool_result.get("content_blocks") or []
    if not _non_text_blocks(blocks):
        return None
    return {
        "role": "user",
        "content": [_openai_chat_part(block) for block in blocks],
    }


def _openai_response_tool_attachment_message(
    tool_result: dict[str, Any],
) -> dict[str, Any] | None:
    blocks = tool_result.get("content_blocks") or []
    if not _non_text_blocks(blocks):
        return None
    return {
        "type": "message",
        "role": "user",
        "content": [_openai_response_part(block) for block in blocks],
    }


def _anthropic_tool_attachment_message(
    tool_result: dict[str, Any],
) -> list[dict[str, Any]]:
    blocks = tool_result.get("content_blocks") or []
    if not _non_text_blocks(blocks):
        return []
    return [_anthropic_part(block) for block in blocks]


def _gemini_tool_attachment_parts(
    tool_result: dict[str, Any],
) -> list[dict[str, Any]]:
    blocks = tool_result.get("content_blocks") or []
    if not _non_text_blocks(blocks):
        return []
    return [_gemini_part(block) for block in blocks]


def _openai_chat_message_content(message: LlmMessage) -> Any:
    blocks = _message_blocks(message)
    if not blocks:
        return coerce_text_content(message.content)
    if message.role.value == "user":
        return [_openai_chat_part(block) for block in blocks]
    _ensure_text_only_blocks(blocks, provider_name="OpenAI chat")
    return extract_text_content(blocks) or ""


def _openai_response_message_content(message: LlmMessage) -> Any:
    blocks = _message_blocks(message)
    if not blocks:
        return coerce_text_content(message.content)
    if message.role.value == "user":
        return [_openai_response_part(block) for block in blocks]
    _ensure_text_only_blocks(blocks, provider_name="OpenAI responses")
    return extract_text_content(blocks) or ""


def _anthropic_message_content(
    message: LlmMessage,
) -> list[dict[str, Any]]:
    role = "assistant" if message.role.value == "assistant" else "user"
    blocks = _message_blocks(message)
    if not blocks:
        return [{"type": "text", "text": coerce_text_content(message.content)}]
    if role == "assistant":
        _ensure_text_only_blocks(blocks, provider_name="Anthropic assistant")
        return [
            {"type": "text", "text": block["text"]}
            for block in blocks
            if block.get("type") == "text"
        ]
    return [_anthropic_part(block) for block in blocks]


def _gemini_message_parts(
    message: LlmMessage,
) -> list[dict[str, Any]]:
    role = "model" if message.role.value == "assistant" else "user"
    blocks = _message_blocks(message)
    if not blocks:
        return [{"text": coerce_text_content(message.content)}]
    if role == "model":
        _ensure_text_only_blocks(blocks, provider_name="Gemini model")
        return [{"text": block["text"]} for block in blocks if block.get("type") == "text"]
    return [_gemini_part(block) for block in blocks]


def _message_blocks(message: LlmMessage) -> list[dict[str, Any]]:
    if isinstance(message.content, dict) and message.content.get("type") == "function_call":
        return []
    try:
        return normalize_content_blocks(message.content)
    except ValueError:
        return []


def _ensure_text_only_blocks(
    blocks: list[dict[str, Any]],
    *,
    provider_name: str,
) -> None:
    if all(block.get("type") == "text" for block in blocks):
        return
    raise RuntimeError(
        f"{provider_name} only supports non-text blocks on user messages.",
    )


def _openai_chat_part(block: dict[str, Any]) -> dict[str, Any]:
    if block["type"] == "text":
        return {"type": "text", "text": block["text"]}
    if block["type"] in {"image_ref", "file_ref"}:
        return {"type": "text", "text": _ref_block_text(block)}
    if block["type"] == "image":
        return {
            "type": "image_url",
            "image_url": {
                "url": _base64_data_url(block["mime_type"], block["data"]),
            },
        }
    if block["type"] == "file":
        return {
            "type": "file",
            "file": {
                "file_data": block["data"],
                "filename": _file_block_name(block),
            },
        }
    raise RuntimeError(f"OpenAI chat does not support '{block['type']}' content blocks yet.")


def _openai_response_part(block: dict[str, Any]) -> dict[str, Any]:
    if block["type"] == "text":
        return {"type": "input_text", "text": block["text"]}
    if block["type"] in {"image_ref", "file_ref"}:
        return {"type": "input_text", "text": _ref_block_text(block)}
    if block["type"] == "image":
        return {
            "type": "input_image",
            "image_url": _base64_data_url(block["mime_type"], block["data"]),
        }
    if block["type"] == "file":
        return {
            "type": "input_file",
            "file_data": block["data"],
            "filename": _file_block_name(block),
        }
    raise RuntimeError(
        f"OpenAI Responses does not support '{block['type']}' content blocks yet.",
    )


def _anthropic_part(block: dict[str, Any]) -> dict[str, Any]:
    if block["type"] == "text":
        return {"type": "text", "text": block["text"]}
    if block["type"] in {"image_ref", "file_ref"}:
        return {"type": "text", "text": _ref_block_text(block)}
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
        if _anthropic_treats_file_as_text(str(block["mime_type"])):
            return {
                "type": "text",
                "text": _anthropic_text_file_content(block),
            }
        if not _anthropic_supports_file_mime_type(str(block["mime_type"])):
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
            "title": _file_block_name(block),
        }
    raise RuntimeError(
        f"Anthropic does not support '{block['type']}' content blocks yet.",
    )


def _gemini_part(block: dict[str, Any]) -> dict[str, Any]:
    if block["type"] == "text":
        return {"text": block["text"]}
    if block["type"] in {"image_ref", "file_ref"}:
        return {"text": _ref_block_text(block)}
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


def _base64_data_url(mime_type: str, data: str) -> str:
    return f"data:{mime_type};base64,{data}"


def _file_block_name(block: dict[str, Any]) -> str:
    name = block.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    mime_type = str(block.get("mime_type") or "").strip().lower()
    if mime_type == "application/pdf":
        return "attachment.pdf"
    return "attachment"


def _ref_block_text(block: dict[str, Any]) -> str:
    block_type = str(block.get("type") or "ref").strip() or "ref"
    fields: list[str] = []
    for key in ("name", "mime_type", "artifact_id"):
        value = block.get(key)
        if isinstance(value, str) and value.strip():
            fields.append(f"{key}={value.strip()}")
    if not fields:
        return f"[{block_type}]"
    return f"[{block_type}: {'; '.join(fields)}]"


def _anthropic_supports_file_mime_type(mime_type: str) -> bool:
    return mime_type.strip().lower() == "application/pdf"


def _anthropic_treats_file_as_text(mime_type: str) -> bool:
    normalized = mime_type.strip().lower()
    return normalized in {
        "text/plain",
        "text/markdown",
        "application/json",
    }


def _anthropic_text_file_content(block: dict[str, Any]) -> str:
    raw_data = str(block.get("data") or "")
    decoded = base64.b64decode(raw_data).decode("utf-8", errors="replace")
    name = _file_block_name(block)
    return f"[file:{name}]\n{decoded}"
