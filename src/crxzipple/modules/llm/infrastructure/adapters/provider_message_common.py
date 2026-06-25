from __future__ import annotations

import base64
import json
from typing import Any

from crxzipple.modules.llm.domain import (
    LlmInputItem,
    LlmInputItemKind,
    LlmMessage,
)
from crxzipple.modules.llm.infrastructure.adapters.adapter_utils import parse_json_arguments
from crxzipple.shared.content_blocks import (
    describe_content_for_text_fallback,
    normalize_content_blocks,
)


def projected_input_items_from_messages(
    messages: tuple[LlmMessage, ...],
    *,
    source: str = "adapter_request_message",
) -> tuple[LlmInputItem, ...]:
    input_items: list[LlmInputItem] = []
    for message in messages:
        metadata = dict(message.metadata)
        tool_call = assistant_function_call(message)
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
        tool_result_payload = tool_result(message)
        if tool_result_payload is not None:
            tool_name = message.name or message.metadata.get("tool_name")
            if isinstance(tool_name, str) and tool_name.strip():
                metadata.setdefault("tool_name", tool_name.strip())
            input_items.append(
                LlmInputItem(
                    kind=LlmInputItemKind.FUNCTION_CALL_OUTPUT,
                    payload={
                        "type": "function_call_output",
                        "call_id": tool_result_payload["call_id"],
                        "output": tool_result_payload["content_blocks"],
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


def assistant_function_call(message: LlmMessage) -> dict[str, Any] | None:
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
    arguments_text = json_text(arguments)
    return {
        "call_id": call_id.strip(),
        "name": name.strip(),
        "arguments_text": arguments_text,
        "arguments_value": parse_json_arguments(arguments),
    }


def tool_result(message: LlmMessage) -> dict[str, Any] | None:
    if not message.tool_call_id or message.role.value != "tool":
        return None
    blocks = message_blocks(message)
    output_text = describe_content_for_text_fallback(blocks)
    if not output_text.strip():
        output_text = "Tool completed."
    return {
        "call_id": message.tool_call_id,
        "output_text": output_text,
        "content_blocks": blocks,
        "metadata": dict(message.metadata),
    }


def json_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value if value is not None else {}, ensure_ascii=True, sort_keys=True)


def coerce_json_like_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {
            str(key): coerce_json_like_value(item)
            for key, item in value.items()
            if item is not None
        }
    if isinstance(value, (list, tuple)):
        return [coerce_json_like_value(item) for item in value]
    return str(value)


def non_text_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [block for block in blocks if block.get("type") not in {"text"}]


def message_blocks(message: LlmMessage) -> list[dict[str, Any]]:
    if isinstance(message.content, dict) and message.content.get("type") == "function_call":
        return []
    try:
        return normalize_content_blocks(message.content)
    except ValueError:
        return []


def ensure_text_only_blocks(
    blocks: list[dict[str, Any]],
    *,
    provider_name: str,
) -> None:
    if all(block.get("type") == "text" for block in blocks):
        return
    raise RuntimeError(
        f"{provider_name} only supports non-text blocks on user messages.",
    )


def base64_data_url(mime_type: str, data: str) -> str:
    return f"data:{mime_type};base64,{data}"


def file_block_name(block: dict[str, Any]) -> str:
    name = block.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    mime_type = str(block.get("mime_type") or "").strip().lower()
    if mime_type == "application/pdf":
        return "attachment.pdf"
    return "attachment"


def ref_block_text(block: dict[str, Any]) -> str:
    block_type = str(block.get("type") or "ref").strip() or "ref"
    fields: list[str] = []
    for key in ("name", "mime_type", "artifact_id"):
        value = block.get(key)
        if isinstance(value, str) and value.strip():
            fields.append(f"{key}={value.strip()}")
    if not fields:
        return f"[{block_type}]"
    return f"[{block_type}: {'; '.join(fields)}]"


def anthropic_supports_file_mime_type(mime_type: str) -> bool:
    return mime_type.strip().lower() == "application/pdf"


def anthropic_treats_file_as_text(mime_type: str) -> bool:
    normalized = mime_type.strip().lower()
    return normalized in {
        "text/plain",
        "text/markdown",
        "application/json",
    }


def anthropic_text_file_content(block: dict[str, Any]) -> str:
    raw_data = str(block.get("data") or "")
    decoded = base64.b64decode(raw_data).decode("utf-8", errors="replace")
    name = file_block_name(block)
    return f"[file:{name}]\n{decoded}"
