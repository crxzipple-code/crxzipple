from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from crxzipple.modules.llm.domain import (
    LlmInputItem,
    LlmInputItemKind,
    LlmMessage,
    LlmMessageRole,
)


def provider_context_messages(request: Any) -> tuple[LlmMessage, ...]:
    """Return explicit provider context messages only."""

    return tuple(getattr(request, "provider_context_messages", ()) or ())


def provider_safe_input_metadata(metadata: Mapping[str, object]) -> dict[str, object]:
    allowed_keys = {
        "node_id",
        "owner",
        "kind",
        "session_item_id",
        "sequence_no",
        "tool_call_id",
        "tool_name",
        "tool_run_id",
        "llm_response_item_id",
    }
    return {
        key: value
        for key, value in metadata.items()
        if key in allowed_keys and value not in (None, "", {}, [])
    }


def messages_from_projected_input_items(
    input_items: tuple[LlmInputItem, ...],
    *,
    fallback_messages: tuple[LlmMessage, ...] = (),
) -> tuple[LlmMessage, ...]:
    if not input_items:
        return fallback_messages
    messages: list[LlmMessage] = []
    for item in input_items:
        metadata = {
            **provider_safe_input_metadata(item.metadata),
            "input_item_kind": item.kind.value,
            "input_item_source": item.source,
        }
        payload = dict(item.payload)
        if item.kind is LlmInputItemKind.MESSAGE:
            role_value = str(payload.get("role") or "user")
            try:
                role = LlmMessageRole(role_value)
            except ValueError:
                role = LlmMessageRole.USER
            messages.append(
                LlmMessage(
                    role=role,
                    content=payload.get("content", ""),
                    name=(
                        str(payload["name"])
                        if payload.get("name") is not None
                        else None
                    ),
                    metadata=metadata,
                ),
            )
            continue
        if item.kind is LlmInputItemKind.FUNCTION_CALL:
            call_id = str(payload.get("call_id") or payload.get("id") or "")
            name = str(payload.get("name") or payload.get("tool_name") or "")
            arguments = payload.get("arguments")
            messages.append(
                LlmMessage(
                    role=LlmMessageRole.ASSISTANT,
                    content={
                        "type": "function_call",
                        "call_id": call_id,
                        "name": name,
                        "arguments": (
                            arguments if isinstance(arguments, dict) else {}
                        ),
                    },
                    tool_call_id=call_id or None,
                    metadata=metadata,
                ),
            )
            continue
        if item.kind is LlmInputItemKind.FUNCTION_CALL_OUTPUT:
            call_id = str(payload.get("call_id") or "")
            output = payload.get("output", payload.get("content", ""))
            tool_name = payload.get("name") or payload.get("tool_name")
            messages.append(
                LlmMessage(
                    role=LlmMessageRole.TOOL,
                    content=output,
                    name=(
                        str(tool_name).strip()
                        if isinstance(tool_name, str) and str(tool_name).strip()
                        else None
                    ),
                    tool_call_id=call_id or None,
                    metadata=metadata,
                ),
            )
            continue
        if item.kind is LlmInputItemKind.REASONING:
            summary = payload.get("summary", payload.get("text", ""))
            if isinstance(summary, list):
                fragments: list[str] = []
                for part in summary:
                    if isinstance(part, dict) and part.get("text") is not None:
                        fragments.append(str(part["text"]))
                        continue
                    if part is not None:
                        fragments.append(str(part))
                summary = "\n".join(fragment for fragment in fragments if fragment)
            messages.append(
                LlmMessage(
                    role=LlmMessageRole.ASSISTANT,
                    content=str(summary),
                    metadata=metadata,
                ),
            )
            continue
        messages.append(
            LlmMessage(
                role=LlmMessageRole.ASSISTANT,
                content=json.dumps(payload, ensure_ascii=True, sort_keys=True),
                metadata=metadata,
            ),
        )
    return tuple(messages)
