from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
import time
from typing import Any

import httpx
import requests

from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.domain.value_objects import (
    LlmCapability,
    LlmMessage,
    ToolCallIntent,
    ToolSchema,
)
from crxzipple.shared.content_blocks import (
    describe_content_for_text_fallback,
    extract_text_content,
    has_image_content_blocks,
    normalize_content_blocks,
)

OPENAI_TOOL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
OPENAI_TOOL_NAME_MAX_LENGTH = 64
OPENAI_TRANSIENT_HTTP_STATUS_CODES = {408, 429, 500, 502, 503, 504}
OPENAI_TRANSIENT_STREAM_MAX_ATTEMPTS = 3
OPENAI_TRANSIENT_STREAM_INITIAL_BACKOFF_SECONDS = 0.25


class RetryableOpenAIStreamError(RuntimeError):
    """Signals an upstream error that is safe to replay before any output was emitted."""


def is_retryable_openai_stream_exception(exc: BaseException) -> bool:
    if isinstance(exc, RetryableOpenAIStreamError):
        return True
    return isinstance(
        exc,
        (
            requests.ConnectionError,
            requests.Timeout,
            httpx.TimeoutException,
            httpx.TransportError,
        ),
    )


def openai_stream_backoff_seconds(attempt_number: int) -> float:
    if attempt_number <= 1:
        return OPENAI_TRANSIENT_STREAM_INITIAL_BACKOFF_SECONDS
    return OPENAI_TRANSIENT_STREAM_INITIAL_BACKOFF_SECONDS * (2 ** (attempt_number - 1))


def sleep_before_openai_stream_retry(attempt_number: int) -> None:
    time.sleep(openai_stream_backoff_seconds(attempt_number))


async def async_sleep_before_openai_stream_retry(attempt_number: int) -> None:
    await asyncio.sleep(openai_stream_backoff_seconds(attempt_number))


def join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def resolve_credential_binding(
    binding: str | None,
    *,
    required: bool,
    description: str,
    resolved_credential: str | None = None,
) -> str | None:
    if resolved_credential is not None and resolved_credential.strip():
        return resolved_credential.strip()

    normalized_binding = binding.strip() if binding is not None else ""
    if normalized_binding:
        raise RuntimeError(
            f"{description} declares {_credential_binding_label(normalized_binding)} "
            "but no resolved credential was injected.",
        )
    if required:
        raise RuntimeError(f"{description} requires an injected resolved credential.")
    return None


def _credential_binding_label(binding: str) -> str:
    if binding.startswith("env:"):
        env_name = binding.removeprefix("env:").strip()
        return f"credential binding 'env:{env_name}'" if env_name else "env credential binding"
    if binding.startswith("file:"):
        return "file credential binding"
    if binding.startswith("codex_auth_json") or binding in {"codex-cli", "codex_auth_json"}:
        return "Codex auth json credential binding"
    return "credential binding"


def ensure_json_response(
    response: requests.Response,
    *,
    description: str,
) -> dict[str, Any]:
    if response.status_code >= 400:
        raise RuntimeError(
            f"{description} failed with HTTP {response.status_code}: {response.text}",
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"{description} returned invalid JSON: {response.text}",
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{description} returned a non-object JSON payload.")
    return payload


async def httpx_response_text(response: httpx.Response) -> str:
    try:
        return response.text
    except httpx.ResponseNotRead:
        body = await response.aread()
        return body.decode("utf-8", errors="replace")


async def ensure_async_json_response(
    response: httpx.Response,
    *,
    description: str,
) -> dict[str, Any]:
    response_text = await httpx_response_text(response)
    if response.status_code >= 400:
        raise RuntimeError(
            f"{description} failed with HTTP {response.status_code}: {response_text}",
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"{description} returned invalid JSON: {response_text}",
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{description} returned a non-object JSON payload.")
    return payload


def coerce_text_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    return describe_content_for_text_fallback(value)


def parse_json_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw}
        if isinstance(payload, dict):
            return payload
        return {"value": payload}
    return {}


def normalize_openai_tool_name(name: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", name.strip())
    normalized = normalized.strip("_-") or "tool"
    if len(normalized) > OPENAI_TOOL_NAME_MAX_LENGTH:
        normalized = normalized[:OPENAI_TOOL_NAME_MAX_LENGTH].rstrip("_-") or "tool"
    return normalized


def build_openai_tool_name_aliases(
    tool_schemas: tuple[ToolSchema, ...],
) -> dict[str, str]:
    aliases: dict[str, str] = {}
    used_aliases: dict[str, str] = {}
    for tool_schema in tool_schemas:
        original_name = tool_schema.name.strip()
        alias = normalize_openai_tool_name(original_name)
        if alias in used_aliases and used_aliases[alias] != original_name:
            alias = _dedupe_openai_tool_name(alias, original_name)
        aliases[original_name] = alias
        used_aliases[alias] = original_name
    return aliases


def _dedupe_openai_tool_name(base_name: str, original_name: str) -> str:
    suffix = hashlib.sha1(original_name.encode("utf-8")).hexdigest()[:8]
    max_base_length = OPENAI_TOOL_NAME_MAX_LENGTH - len(suffix) - 1
    trimmed_base = base_name[:max_base_length].rstrip("_-") or "tool"
    return f"{trimmed_base}_{suffix}"


def resolve_openai_tool_name(
    name: str,
    *,
    tool_name_aliases: dict[str, str] | None = None,
) -> str:
    normalized_name = name.strip()
    if tool_name_aliases is not None and normalized_name in tool_name_aliases:
        return tool_name_aliases[normalized_name]
    if OPENAI_TOOL_NAME_PATTERN.fullmatch(normalized_name) is not None:
        return normalized_name
    return normalize_openai_tool_name(normalized_name)


def openai_tool_schema(
    tool: ToolSchema,
    *,
    tool_name_aliases: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "type": "function",
        "name": resolve_openai_tool_name(
            tool.name,
            tool_name_aliases=tool_name_aliases,
        ),
        "description": tool.description,
        "parameters": dict(tool.input_schema),
    }


def openai_chat_tool_schema(
    tool: ToolSchema,
    *,
    tool_name_aliases: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": resolve_openai_tool_name(
                tool.name,
                tool_name_aliases=tool_name_aliases,
            ),
            "description": tool.description,
            "parameters": dict(tool.input_schema),
        },
    }


def anthropic_tool_schema(tool: ToolSchema) -> dict[str, Any]:
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": dict(tool.input_schema),
    }


def gemini_tool_schema(tool: ToolSchema) -> dict[str, Any]:
    return {
        "name": tool.name,
        "description": tool.description,
        "parameters": dict(tool.input_schema),
    }


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


def openai_response_input_items(
    messages: tuple[LlmMessage, ...],
    *,
    tool_name_aliases: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for message in messages:
        tool_call = _assistant_function_call(message)
        if tool_call is not None:
            payloads.append(
                {
                    "type": "function_call",
                    "call_id": tool_call["call_id"],
                    "name": resolve_openai_tool_name(
                        tool_call["name"],
                        tool_name_aliases=tool_name_aliases,
                    ),
                    "arguments": tool_call["arguments_text"],
                },
            )
            continue

        tool_result = _tool_result(message)
        if tool_result is not None:
            payloads.append(
                {
                    "type": "function_call_output",
                    "call_id": tool_result["call_id"],
                    "output": tool_result["output_text"],
                },
            )
            attachment_payload = _openai_response_tool_attachment_message(tool_result)
            if attachment_payload is not None:
                payloads.append(attachment_payload)
            continue

        payload: dict[str, Any] = {
            "role": message.role.value,
            "content": _openai_response_message_content(message),
        }
        if message.name is not None:
            payload["name"] = message.name
        payloads.append(payload)
    return payloads


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
            _append_anthropic_tool_result_block(
                payloads,
                {
                    "type": "tool_result",
                    "tool_use_id": tool_result["call_id"],
                    "content": tool_result["output_text"],
                },
            )
            attachment_payload = _anthropic_tool_attachment_message(tool_result)
            if attachment_payload is not None:
                payloads.append(attachment_payload)
            continue

        role = "assistant" if message.role.value == "assistant" else "user"
        content_blocks = _anthropic_message_content(message, role=role)
        if role == "assistant":
            for block in content_blocks:
                _append_anthropic_assistant_block(payloads, block)
        else:
            payloads.append({"role": "user", "content": content_blocks})
    return payloads


def _assistant_function_call(message: LlmMessage) -> dict[str, Any] | None:
    if message.role.value != "assistant":
        return None
    if not isinstance(message.content, dict):
        return None
    if message.content.get("type") != "function_call":
        return None
    call_id = message.content.get("call_id") or message.tool_call_id
    name = message.content.get("name")
    if not isinstance(call_id, str) or not call_id.strip():
        return None
    if not isinstance(name, str) or not name.strip():
        return None
    arguments = message.content.get("arguments", {})
    if isinstance(arguments, str):
        arguments_text = arguments
    else:
        arguments_text = json.dumps(arguments, ensure_ascii=False, sort_keys=True)
    return {
        "call_id": call_id.strip(),
        "name": name.strip(),
        "arguments_text": arguments_text,
        "arguments_value": parse_json_arguments(arguments),
    }


def _tool_result(message: LlmMessage) -> dict[str, Any] | None:
    if message.role.value != "tool":
        return None
    call_id = message.tool_call_id
    if call_id is None or not call_id.strip():
        return None
    blocks = _message_blocks(message)
    output_text = describe_content_for_text_fallback(blocks)
    if not output_text.strip():
        output_text = "Tool completed."
    return {
        "call_id": call_id.strip(),
        "output_text": output_text,
        "content_blocks": blocks,
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
    block: dict[str, Any],
) -> None:
    if (
        payloads
        and payloads[-1].get("role") == "user"
        and all(
            isinstance(item, dict) and item.get("type") == "tool_result"
            for item in payloads[-1].get("content", [])
        )
    ):
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
            tool_name = message.name
            if tool_name is None:
                metadata_tool_name = message.metadata.get("tool_name")
                if isinstance(metadata_tool_name, str) and metadata_tool_name.strip():
                    tool_name = metadata_tool_name.strip()
            if tool_name is None:
                tool_name = "tool"
            _append_gemini_tool_response_part(
                contents,
                {
                    "functionResponse": {
                        "id": tool_result["call_id"],
                        "name": tool_name,
                        "response": {
                            "result": _coerce_json_like_value(
                                tool_result["output_text"],
                            ),
                        },
                    },
                },
            )
            attachment_parts = _gemini_tool_attachment_parts(tool_result)
            for part in attachment_parts:
                _append_gemini_user_text_part(contents, part)
            continue

        role = "model" if message.role.value == "assistant" else "user"
        parts = _gemini_message_parts(message, role=role)
        if role == "model":
            for part in parts:
                _append_gemini_model_part(contents, part)
        else:
            for part in parts:
                _append_gemini_user_text_part(contents, part)
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
    part: dict[str, Any],
) -> None:
    if (
        contents
        and contents[-1].get("role") == "user"
        and not any(
            isinstance(existing, dict) and existing.get("functionResponse") is not None
            for existing in contents[-1].get("parts", [])
        )
    ):
        contents[-1].setdefault("parts", []).append(part)
        return
    contents.append({"role": "user", "parts": [part]})


def _append_gemini_tool_response_part(
    contents: list[dict[str, Any]],
    part: dict[str, Any],
) -> None:
    if (
        contents
        and contents[-1].get("role") == "user"
        and all(
            isinstance(existing, dict) and existing.get("functionResponse") is not None
            for existing in contents[-1].get("parts", [])
        )
    ):
        contents[-1].setdefault("parts", []).append(part)
        return
    contents.append({"role": "user", "parts": [part]})


def _coerce_json_like_value(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    if isinstance(value, dict):
        if (
            isinstance(value.get("data"), str)
            and value.get("data")
            and str(value.get("encoding", "")).strip().lower() == "base64"
        ):
            sanitized = {
                str(key): _coerce_json_like_value(item)
                for key, item in value.items()
                if key != "data"
            }
            sanitized["attachment_in_blocks"] = True
            return sanitized
        return {
            str(key): _coerce_json_like_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_coerce_json_like_value(item) for item in value]
    return value


def _non_text_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [block for block in blocks if block.get("type") != "text"]


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
        "role": "user",
        "content": [_openai_response_part(block) for block in blocks],
    }


def _anthropic_tool_attachment_message(
    tool_result: dict[str, Any],
) -> dict[str, Any] | None:
    blocks = tool_result.get("content_blocks") or []
    if not _non_text_blocks(blocks):
        return None
    return {
        "role": "user",
        "content": [_anthropic_part(block) for block in blocks],
    }


def _gemini_tool_attachment_parts(
    tool_result: dict[str, Any],
) -> list[dict[str, Any]]:
    blocks = tool_result.get("content_blocks") or []
    if not _non_text_blocks(blocks):
        return []
    return [_gemini_part(block) for block in blocks]


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


def default_base_url(profile: LlmProfile, fallback: str) -> str:
    return profile.base_url or fallback


def ensure_image_input_supported(
    profile: LlmProfile,
    messages: tuple[LlmMessage, ...],
) -> None:
    if not any(has_image_content_blocks(message.content) for message in messages):
        return
    if LlmCapability.VISION_INPUT not in profile.capabilities:
        raise RuntimeError(
            f"LLM profile '{profile.id}' does not support vision input.",
        )


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
    *,
    role: str,
) -> list[dict[str, Any]]:
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
    *,
    role: str,
) -> list[dict[str, Any]]:
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
