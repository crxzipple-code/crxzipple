from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

import requests

from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.domain.value_objects import LlmMessage, ToolCallIntent, ToolSchema

OPENAI_TOOL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
OPENAI_TOOL_NAME_MAX_LENGTH = 64


def join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def default_codex_auth_json_path() -> Path:
    codex_home = os.getenv("CODEX_HOME")
    if isinstance(codex_home, str) and codex_home.strip():
        return Path(codex_home).expanduser() / "auth.json"
    return Path("~/.codex/auth.json").expanduser()


def load_codex_auth_json_access_token(path: Path) -> str | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid codex auth json at '{path}'.") from exc

    if not isinstance(payload, dict):
        return None
    tokens = payload.get("tokens")
    if not isinstance(tokens, dict):
        return None
    access_token = tokens.get("access_token")
    if not isinstance(access_token, str) or not access_token.strip():
        return None
    return access_token.strip()


def resolve_credential_binding(
    binding: str | None,
    *,
    required: bool,
    description: str,
) -> str | None:
    if binding is None:
        if required:
            raise RuntimeError(f"{description} requires a credential binding.")
        return None

    normalized = binding.strip()
    if not normalized:
        if required:
            raise RuntimeError(f"{description} has an empty credential binding.")
        return None

    if normalized.startswith("env:"):
        env_name = normalized.removeprefix("env:").strip()
        if not env_name:
            raise RuntimeError(f"{description} has an invalid env credential binding.")
        value = os.getenv(env_name)
        if value is None or not value.strip():
            raise RuntimeError(
                f"{description} could not resolve env var '{env_name}'.",
            )
        return value.strip()

    codex_binding_prefixes = (
        "codex_auth_json:",
        "codex-auth-json:",
        "codex_cli:",
        "codex-cli:",
    )
    if normalized in {"codex_auth_json", "codex-auth-json", "codex_cli", "codex-cli"}:
        path = default_codex_auth_json_path()
        token = load_codex_auth_json_access_token(path)
        if token is None:
            raise RuntimeError(
                f"{description} could not resolve a Codex access token from '{path}'.",
            )
        return token
    if normalized.startswith(codex_binding_prefixes):
        binding_name, raw_path = normalized.split(":", 1)
        del binding_name
        path = Path(raw_path.strip()).expanduser()
        if not raw_path.strip():
            raise RuntimeError(
                f"{description} has an invalid Codex auth json credential binding.",
            )
        token = load_codex_auth_json_access_token(path)
        if token is None:
            raise RuntimeError(
                f"{description} could not resolve a Codex access token from '{path}'.",
            )
        return token

    return normalized


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


def coerce_text_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


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
            continue

        payload: dict[str, Any] = {
            "role": message.role.value,
            "content": coerce_text_content(message.content),
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
            continue

        payload: dict[str, Any] = {
            "role": message.role.value,
            "content": coerce_text_content(message.content),
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
            continue

        role = "assistant" if message.role.value == "assistant" else "user"
        block = {
            "type": "text",
            "text": coerce_text_content(message.content),
        }
        if role == "assistant":
            _append_anthropic_assistant_block(payloads, block)
        else:
            payloads.append({"role": "user", "content": [block]})
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


def _tool_result(message: LlmMessage) -> dict[str, str] | None:
    if message.role.value != "tool":
        return None
    call_id = message.tool_call_id
    if call_id is None or not call_id.strip():
        return None
    return {
        "call_id": call_id.strip(),
        "output_text": coerce_text_content(message.content),
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
                            "result": _coerce_json_like_value(message.content),
                        },
                    },
                },
            )
            continue

        role = "model" if message.role.value == "assistant" else "user"
        part = {"text": coerce_text_content(message.content)}
        if role == "model":
            _append_gemini_model_part(contents, part)
        else:
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
    return value


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
