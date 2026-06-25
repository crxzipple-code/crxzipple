from __future__ import annotations

from collections.abc import Mapping

from crxzipple.modules.llm.domain import (
    LlmCapability,
    LlmInputItem,
    LlmInputItemKind,
    LlmMessage,
    LlmMessageRole,
)


def messages_from_runtime_input_items(
    input_items: tuple[LlmInputItem, ...],
    *,
    fallback_messages: tuple[LlmMessage, ...] = (),
) -> tuple[LlmMessage, ...]:
    if not input_items:
        return fallback_messages
    messages: list[LlmMessage] = []
    for item in input_items:
        payload = dict(item.payload)
        metadata = dict(item.metadata)
        if item.kind is LlmInputItemKind.MESSAGE:
            messages.append(
                LlmMessage(
                    role=message_role_from_payload(payload.get("role")),
                    content=payload.get("content", ""),
                    name=metadata_text(payload.get("name")),
                    metadata=metadata,
                ),
            )
            continue
        if item.kind is LlmInputItemKind.FUNCTION_CALL:
            call_id = str(payload.get("call_id") or "").strip()
            messages.append(
                LlmMessage(
                    role=LlmMessageRole.ASSISTANT,
                    content={
                        "type": "function_call",
                        "call_id": call_id,
                        "name": str(payload.get("name") or "").strip(),
                        "arguments": (
                            dict(payload.get("arguments"))
                            if isinstance(payload.get("arguments"), dict)
                            else {}
                        ),
                    },
                    tool_call_id=call_id or None,
                    metadata=metadata,
                ),
            )
            continue
        if item.kind is LlmInputItemKind.FUNCTION_CALL_OUTPUT:
            messages.append(
                LlmMessage(
                    role=LlmMessageRole.TOOL,
                    content=payload.get("output", ""),
                    name=metadata_text(metadata.get("tool_name")),
                    tool_call_id=metadata_text(payload.get("call_id")),
                    metadata=metadata,
                ),
            )
            continue
        if item.kind is LlmInputItemKind.REASONING:
            messages.append(
                LlmMessage(
                    role=LlmMessageRole.ASSISTANT,
                    content=payload.get("content", ""),
                    metadata={**metadata, "kind": "reasoning"},
                ),
            )
    return tuple(messages)


def runtime_input_items_from_projected_payloads(
    projected_input_items: tuple[Mapping[str, object], ...],
    *,
    default_source: str = "context_slice",
) -> tuple[LlmInputItem, ...]:
    """Build canonical runtime input items from Context Slice projection payloads."""

    items: list[LlmInputItem] = []
    for raw in projected_input_items:
        kind = input_item_kind_from_text(raw.get("kind"))
        payload = raw.get("payload")
        if kind is None or not isinstance(payload, Mapping):
            continue
        metadata = raw.get("metadata")
        source = metadata_text(raw.get("source")) or default_source
        items.append(
            LlmInputItem(
                kind=kind,
                payload=dict(payload),
                source=source,
                metadata=dict(metadata) if isinstance(metadata, Mapping) else {},
            ),
        )
    return tuple(items)


def provider_context_messages_from_messages(
    messages: tuple[LlmMessage, ...],
) -> tuple[LlmMessage, ...]:
    provider_context_messages: list[LlmMessage] = []
    for message in messages:
        if message.role is not LlmMessageRole.SYSTEM:
            continue
        if empty_content(message.content):
            continue
        metadata = dict(message.metadata)
        metadata.setdefault("provider_context_kind", "runtime_instruction")
        metadata.setdefault("source", "runtime_request_draft_message")
        provider_context_messages.append(
            LlmMessage(
                role=message.role,
                content=message.content,
                name=message.name,
                tool_call_id=message.tool_call_id,
                metadata=metadata,
            ),
        )
    return tuple(provider_context_messages)


def sanitize_runtime_input_items_for_capabilities(
    input_items: tuple[LlmInputItem, ...],
    *,
    llm_capabilities: tuple[LlmCapability, ...],
) -> tuple[LlmInputItem, ...]:
    if LlmCapability.VISION_INPUT in set(llm_capabilities):
        return input_items
    sanitized: list[LlmInputItem] = []
    for item in input_items:
        payload = dict(item.payload) if isinstance(item.payload, Mapping) else item.payload
        if isinstance(payload, dict):
            if item.kind is LlmInputItemKind.MESSAGE:
                payload["content"] = remove_vision_blocks(payload.get("content"))
            elif item.kind is LlmInputItemKind.FUNCTION_CALL_OUTPUT:
                payload["output"] = remove_vision_blocks(payload.get("output"))
        sanitized.append(
            LlmInputItem(
                kind=item.kind,
                payload=payload,
                source=normalize_input_item_source(item.source),
                metadata=normalize_input_item_metadata(item.metadata),
            ),
        )
    return tuple(sanitized)


def runtime_input_item_mode_metadata(
    input_items: tuple[LlmInputItem, ...],
) -> dict[str, object]:
    source_counts: dict[str, int] = {}
    kind_counts: dict[str, int] = {}
    for item in input_items:
        source_counts[item.source] = source_counts.get(item.source, 0) + 1
        kind_counts[item.kind.value] = kind_counts.get(item.kind.value, 0) + 1
    return {
        "input_mode": "runtime_transcript" if input_items else "empty",
        "input_item_count": len(input_items),
        "input_item_kind_counts": kind_counts,
        "input_item_source_counts": source_counts,
    }


def runtime_transcript_input_items_from_messages(
    *,
    input_items: tuple[LlmInputItem, ...],
    messages: tuple[LlmMessage, ...],
) -> tuple[LlmInputItem, ...]:
    if input_items:
        return input_items
    return tuple(
        LlmInputItem(
            kind=LlmInputItemKind.MESSAGE,
            payload={
                "role": message.role.value,
                "content": message.content,
                **({"name": message.name} if message.name is not None else {}),
            },
            source="runtime_transcript",
            metadata=dict(message.metadata),
        )
        for message in messages
        if message.role is not LlmMessageRole.SYSTEM
        and not empty_content(message.content)
    )


def runtime_transcript_policy(
    transcript_policy: Mapping[str, object],
    *,
    require_tool_call: bool = False,
) -> dict[str, object]:
    policy = dict(transcript_policy)
    if require_tool_call:
        policy["require_tool_call"] = True
    return policy


def normalize_input_item_source(source: str) -> str:
    if source == "context_slice":
        return "runtime_transcript"
    return source


def normalize_input_item_metadata(metadata: Mapping[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in metadata.items()
        if not key.startswith("context_slice")
    }


def remove_vision_blocks(value: object) -> object:
    if isinstance(value, list):
        filtered: list[object] = []
        omitted_names: list[str] = []
        for block in value:
            if not isinstance(block, Mapping):
                filtered.append(block)
                continue
            block_type = str(block.get("type") or "").strip().lower()
            if block_type in {"image", "image_ref"}:
                name = metadata_text(block.get("name")) or block_type
                omitted_names.append(name)
                continue
            filtered.append(dict(block))
        if filtered:
            if omitted_names:
                filtered.append(
                    {
                        "type": "text",
                        "text": "[image omitted: model does not support vision input]",
                    },
                )
            return filtered
        if omitted_names:
            return [
                {
                    "type": "text",
                    "text": "[image omitted: model does not support vision input]",
                },
            ]
        return filtered
    if isinstance(value, Mapping):
        block_type = str(value.get("type") or "").strip().lower()
        if block_type in {"image", "image_ref"}:
            return {
                "type": "text",
                "text": "[image omitted: model does not support vision input]",
            }
        return {key: remove_vision_blocks(item) for key, item in value.items()}
    return value


def message_role_from_payload(value: object) -> LlmMessageRole:
    try:
        return LlmMessageRole(str(value or "user").strip().lower())
    except ValueError:
        return LlmMessageRole.USER


def input_item_kind_from_text(value: object) -> LlmInputItemKind | None:
    text = metadata_text(value)
    if text is None:
        return None
    try:
        return LlmInputItemKind(text)
    except ValueError:
        return None


def metadata_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def empty_content(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list | tuple | dict):
        return len(value) == 0
    return False


__all__ = [
    "empty_content",
    "input_item_kind_from_text",
    "message_role_from_payload",
    "messages_from_runtime_input_items",
    "metadata_text",
    "normalize_input_item_metadata",
    "normalize_input_item_source",
    "provider_context_messages_from_messages",
    "remove_vision_blocks",
    "runtime_input_item_mode_metadata",
    "runtime_input_items_from_projected_payloads",
    "runtime_transcript_input_items_from_messages",
    "runtime_transcript_policy",
    "sanitize_runtime_input_items_for_capabilities",
]
