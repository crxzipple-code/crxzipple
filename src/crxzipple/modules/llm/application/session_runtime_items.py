from __future__ import annotations

import json

from crxzipple.modules.llm.application.tool_result_model_text import (
    render_tool_result_model_text,
)
from crxzipple.modules.llm.domain import (
    LlmInputItem,
    LlmInputItemKind,
    LlmMessage,
    LlmMessageRole,
)
from crxzipple.modules.session.domain import (
    SessionItem,
    SessionItemKind,
    SessionItemPhase,
)
from crxzipple.shared.content_blocks import (
    content_blocks_from_payload,
    describe_content_for_text_fallback,
    extract_text_content,
    text_content_block,
)


def is_current_turn_progress_item(item: SessionItem) -> bool:
    if item.kind is SessionItemKind.AGENT_PROGRESS:
        return has_replayable_content(item)
    if item.kind is SessionItemKind.REASONING:
        return has_replayable_content(item)
    if (
        item.kind is SessionItemKind.ASSISTANT_MESSAGE
        and item.role == "assistant"
        and item.phase is not SessionItemPhase.FINAL_ANSWER
    ):
        return has_replayable_content(item)
    return False


def item_to_llm_message(item: SessionItem) -> LlmMessage:
    role = item_role(item)
    tool_name = item.tool_name
    metadata: dict[str, object] = {
        "session_item_id": item.id,
        "session_id": item.session_id,
        "sequence_no": item.sequence_no,
        "kind": item.kind.value,
        "phase": item.phase.value,
        "source_module": item.source_module,
        "source_kind": item.source_kind,
        "source_id": item.source_id,
    }
    if item.provider_item_id is not None:
        metadata["provider_item_id"] = item.provider_item_id
    if item.provider_item_type is not None:
        metadata["provider_item_type"] = item.provider_item_type
    if item.call_id is not None:
        metadata["tool_call_id"] = item.call_id
    if tool_name is not None:
        metadata["tool_name"] = tool_name
    tool_status = item.metadata.get("tool_status")
    if isinstance(tool_status, str) and tool_status.strip():
        metadata["tool_status"] = tool_status.strip()
    if item.kind is SessionItemKind.TOOL_RESULT and "error" in item.content_payload:
        metadata["tool_error"] = item.content_payload["error"]
    return LlmMessage(
        role=role,
        content=extract_item_content(item, role=role),
        name=tool_name if role is LlmMessageRole.TOOL else None,
        tool_call_id=(
            item.call_id
            if item.kind in {SessionItemKind.TOOL_CALL, SessionItemKind.TOOL_RESULT}
            else None
        ),
        metadata=metadata,
    )


def item_to_llm_input_item(
    item: SessionItem,
    *,
    message: LlmMessage,
) -> LlmInputItem:
    metadata = dict(message.metadata)
    if item.kind is SessionItemKind.TOOL_CALL:
        content = message.content if isinstance(message.content, dict) else {}
        return LlmInputItem(
            kind=LlmInputItemKind.FUNCTION_CALL,
            payload={
                "type": "function_call",
                "call_id": str(
                    item.call_id
                    or content.get("call_id")
                    or item.provider_item_id
                    or item.id,
                ),
                "name": str(
                    item.tool_name
                    or content.get("name")
                    or item.content_payload.get("tool_name")
                    or "",
                ),
                "arguments": (
                    content.get("arguments")
                    if isinstance(content.get("arguments"), dict)
                    else {}
                ),
            },
            source="session_item",
            metadata=metadata,
        )
    if item.kind is SessionItemKind.TOOL_RESULT:
        return LlmInputItem(
            kind=LlmInputItemKind.FUNCTION_CALL_OUTPUT,
            payload={
                "type": "function_call_output",
                "call_id": str(
                    item.call_id
                    or message.tool_call_id
                    or item.provider_item_id
                    or item.id,
                ),
                "output": message.content,
            },
            source="session_item",
            metadata=metadata,
        )
    if item.kind is SessionItemKind.REASONING:
        return LlmInputItem(
            kind=LlmInputItemKind.REASONING,
            payload={
                "type": "reasoning",
                "content": message.content,
            },
            source="session_item",
            metadata=metadata,
        )
    if item.kind is SessionItemKind.PROVIDER_EXTERNAL_ACTIVITY:
        payload = dict(item.content_payload)
        if item.provider_item_type is not None:
            payload.setdefault("type", item.provider_item_type)
        return LlmInputItem(
            kind=LlmInputItemKind.PROVIDER_EXTERNAL_ITEM,
            payload=payload,
            source="session_item",
            metadata=metadata,
        )
    return LlmInputItem(
        kind=LlmInputItemKind.MESSAGE,
        payload={
            "role": message.role.value,
            "content": message.content,
            **({"name": message.name} if message.name is not None else {}),
        },
        source="session_item",
        metadata=metadata,
    )


def item_role(item: SessionItem) -> LlmMessageRole:
    if item.role is not None:
        try:
            return LlmMessageRole(item.role)
        except ValueError:
            pass
    if item.kind is SessionItemKind.TOOL_RESULT:
        return LlmMessageRole.TOOL
    return LlmMessageRole.ASSISTANT


def extract_item_content(
    item: SessionItem,
    *,
    role: LlmMessageRole,
) -> object:
    if item.kind is SessionItemKind.TOOL_CALL:
        return {
            "type": "function_call",
            "call_id": item.call_id or item.provider_item_id or item.id,
            "name": item.tool_name or item.content_payload.get("tool_name") or "",
            "arguments": (
                dict(item.content_payload.get("arguments"))
                if isinstance(item.content_payload.get("arguments"), dict)
                else {}
            ),
        }
    if role is LlmMessageRole.TOOL:
        compact_result = compact_tool_result_payload(item.content_payload)
        if compact_result is not None:
            return compact_result
        blocks = content_blocks_from_payload(item.content_payload)
        if blocks:
            return blocks
        content = item.content_payload.get("content")
        if isinstance(content, list):
            return content
        if "error" in item.content_payload:
            return [
                text_content_block(
                    describe_content_for_text_fallback(item.content_payload["error"]),
                ),
            ]
        return [text_content_block("Tool completed.")]
    blocks = content_blocks_from_payload(item.content_payload)
    if blocks:
        return blocks
    text = item.content_payload.get("text")
    if isinstance(text, str) and text.strip():
        return [text_content_block(text)]
    return [
        text_content_block(
            json.dumps(
                item.content_payload,
                ensure_ascii=True,
                sort_keys=True,
            ),
        ),
    ]


def has_replayable_content(item: SessionItem) -> bool:
    blocks = content_blocks_from_payload(item.content_payload)
    text_content = extract_text_content(blocks if blocks else item.content_payload)
    if text_content is not None and text_content.strip():
        return True
    if blocks:
        return True
    text = item.content_payload.get("text")
    return isinstance(text, str) and bool(text.strip())


def dedupe_adjacent_assistant_progress(
    items: tuple[SessionItem, ...],
) -> tuple[SessionItem, ...]:
    deduped: list[SessionItem] = []
    previous_progress_text: str | None = None
    for item in items:
        if (
            item.kind is SessionItemKind.ASSISTANT_MESSAGE
            and item.role == "assistant"
            and item.phase is not SessionItemPhase.FINAL_ANSWER
        ):
            text = session_item_text_fingerprint(item)
            if text is not None and text == previous_progress_text:
                continue
            previous_progress_text = text
        else:
            previous_progress_text = None
        deduped.append(item)
    return tuple(deduped)


def session_item_text_fingerprint(item: SessionItem) -> str | None:
    blocks = content_blocks_from_payload(item.content_payload)
    text_content = extract_text_content(blocks if blocks else item.content_payload)
    if text_content is not None and text_content.strip():
        return text_content.strip()
    text = item.content_payload.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return None


def compact_tool_result_payload(
    payload: dict[str, object],
) -> list[dict[str, object]] | None:
    content = render_tool_result_model_text(payload)
    if content is None:
        return None
    return [text_content_block(content)]


__all__ = [
    "compact_tool_result_payload",
    "dedupe_adjacent_assistant_progress",
    "extract_item_content",
    "has_replayable_content",
    "is_current_turn_progress_item",
    "item_role",
    "item_to_llm_input_item",
    "item_to_llm_message",
]
