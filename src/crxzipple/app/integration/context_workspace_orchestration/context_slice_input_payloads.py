"""Provider input payload builders for individual context slice items."""

from __future__ import annotations

import json

from .context_slice_refs import metadata_text_value


def context_slice_item_input_payloads(
    item: object,
    owner_ref: dict[str, object],
) -> tuple[dict[str, object], ...]:
    kind = str(getattr(item, "kind", "") or "").strip()
    item_metadata = getattr(item, "metadata", None)
    if (
        isinstance(item_metadata, dict)
        and item_metadata.get("owner_resolution") == "owner_unresolved"
    ):
        return ()
    session_item_kind = metadata_text_value(owner_ref.get("kind"))
    source_kind = metadata_text_value(owner_ref.get("source_kind"))
    provider_item_type = metadata_text_value(owner_ref.get("provider_item_type"))
    runtime_semantic_kind = metadata_text_value(owner_ref.get("runtime_semantic_kind"))
    if owner_ref.get("model_visible") is False:
        return ()
    if kind in {"reasoning"}:
        return ()
    if session_item_kind in {
        "reasoning",
        "provider_external_activity",
        "runtime_notice",
        "runtime_error",
        "unknown",
    }:
        return ()
    if runtime_semantic_kind in {"runtime.reasoning"}:
        return ()
    if provider_item_type == "reasoning":
        return ()
    if source_kind == "approval_request":
        return ()
    tool_call_id = metadata_text_value(
        owner_ref.get("tool_call_id"),
        owner_ref.get("call_id"),
    )
    tool_name = metadata_text_value(
        owner_ref.get("tool_name"),
        owner_ref.get("name"),
    )
    arguments = owner_ref.get("arguments")
    if kind == "tool_interaction" and tool_call_id and tool_name:
        arguments_payload = _tool_interaction_arguments(owner_ref)
        result_content = _sanitize_tool_interaction_output(
            metadata_text_value(owner_ref.get("result_content")) or "",
        )
        return (
            {
                "kind": "function_call",
                "payload": {
                    "type": "function_call",
                    "call_id": tool_call_id,
                    "name": tool_name,
                    "arguments": arguments_payload,
                },
            },
            {
                "kind": "function_call_output",
                "payload": {
                    "type": "function_call_output",
                    "call_id": tool_call_id,
                    "output": result_content,
                },
            },
        )
    role = (
        metadata_text_value(owner_ref.get("role"))
        or _role_from_context_slice_item(item)
        or "user"
    )
    content = getattr(item, "content", None)
    text = metadata_text_value(getattr(item, "text", None)) or ""
    if content in (None, "", [], {}) and not text and not tool_call_id:
        return ()
    if tool_call_id and tool_name and isinstance(arguments, dict):
        return (
            {
                "kind": "function_call",
                "payload": {
                    "type": "function_call",
                    "call_id": tool_call_id,
                    "name": tool_name,
                    "arguments": dict(arguments),
                },
            },
        )
    if role == "tool" or (
        tool_call_id
        and tool_name is None
        and arguments in (None, "", {}, [])
    ):
        return (
            {
                "kind": "function_call_output",
                "payload": {
                    "type": "function_call_output",
                    "call_id": tool_call_id or "",
                    "output": content if content is not None else text,
                },
            },
        )
    if role not in {"user", "assistant", "system"}:
        role = "user"
    return (
        {
            "kind": "message",
            "payload": {
                "role": role,
                "content": content if content is not None else text,
            },
        },
    )


def _tool_interaction_arguments(owner_ref: dict[str, object]) -> dict[str, object]:
    arguments = owner_ref.get("arguments")
    if isinstance(arguments, dict):
        return dict(arguments)
    arguments_json = metadata_text_value(owner_ref.get("arguments_json"))
    if arguments_json is None:
        return {}
    try:
        parsed = json.loads(arguments_json)
    except Exception:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _sanitize_tool_interaction_output(value: str) -> str:
    lines = []
    for line in value.splitlines():
        stripped = line.strip()
        if stripped.startswith("[image:") and stripped.endswith("]"):
            continue
        if stripped.startswith("[file:") and stripped.endswith("]"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _role_from_context_slice_item(item: object) -> str | None:
    kind = str(getattr(item, "kind", "") or "").strip()
    title = str(getattr(item, "title", "") or "").strip().lower()
    if kind == "user_message" or title.startswith("user"):
        return "user"
    if kind == "assistant_message" or title.startswith("assistant"):
        return "assistant"
    if kind == "tool_result" or title.startswith("tool"):
        return "tool"
    return None
