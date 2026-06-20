from __future__ import annotations

import hashlib
import re
from typing import Any

from crxzipple.modules.llm.domain.value_objects import ToolSchema

OPENAI_TOOL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
OPENAI_TOOL_NAME_MAX_LENGTH = 64


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


def _dedupe_openai_tool_name(base_name: str, original_name: str) -> str:
    suffix = hashlib.sha1(original_name.encode("utf-8")).hexdigest()[:8]
    max_base_length = OPENAI_TOOL_NAME_MAX_LENGTH - len(suffix) - 1
    trimmed_base = base_name[:max_base_length].rstrip("_-") or "tool"
    return f"{trimmed_base}_{suffix}"
