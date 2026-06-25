from __future__ import annotations

import hashlib
from typing import Any

from crxzipple.app.integration.context_workspace_session_blocks import (
    blocks_prompt_content,
    content_block_types,
)
from crxzipple.app.integration.context_workspace_session_content_values import (
    json_fragment,
    optional_text,
    text_estimate,
    truncate,
)
from crxzipple.modules.context_workspace.domain import ContextEstimate
from crxzipple.modules.session.domain import SessionItem, SessionItemKind
from crxzipple.shared.content_blocks import (
    FILE_BLOCK_TYPE,
    FILE_REF_BLOCK_TYPE,
    IMAGE_BLOCK_TYPE,
    IMAGE_REF_BLOCK_TYPE,
    content_blocks_from_payload,
    describe_content_for_text_fallback,
)


def message_preview(message: SessionItem) -> str:
    if message.role == "tool":
        return _tool_result_message_preview(message)
    text = describe_content_for_text_fallback(message.content_payload)
    return truncate(text.replace("\n", " "), 320)


def message_prompt_content(message: SessionItem) -> str:
    if (
        message.role == "assistant"
        and message.content_payload.get("type") == "function_call"
    ):
        return _function_call_prompt_content(message)
    if message.role == "tool":
        return _tool_result_prompt_content(message)
    return blocks_prompt_content(content_blocks_from_payload(message.content_payload))


def tool_interaction_prompt_content(
    *,
    tool_name: str,
    tool_call_id: str,
    status: str,
    arguments_json: str,
    result_content: str,
    error_json: str | None,
) -> str:
    lines = [
        "tool_interaction:",
        f"  tool_name: {tool_name}",
    ]
    if tool_call_id:
        lines.append(f"  tool_call_id: {tool_call_id}")
    lines.append(f"  status: {status}")
    if arguments_json:
        lines.append(f"  arguments: {arguments_json}")
    if error_json is not None:
        lines.append(f"  error: {error_json}")
    if result_content:
        lines.append("  result:")
        lines.extend(f"    {line}" for line in result_content.splitlines())
    return "\n".join(lines)


def is_function_call_message(message: SessionItem) -> bool:
    return message.role == "assistant" and (
        message.kind is SessionItemKind.TOOL_CALL
        or message.content_payload.get("type") == "function_call"
    )


def tool_call_id(message: SessionItem) -> str | None:
    return (
        optional_text(message.metadata.get("tool_call_id"))
        or optional_text(message.content_payload.get("call_id"))
        or optional_text(message.content_payload.get("tool_call_id"))
    )


def tool_name(message: SessionItem) -> str | None:
    return (
        optional_text(message.metadata.get("tool_name"))
        or optional_text(message.content_payload.get("name"))
        or optional_text(message.content_payload.get("tool_name"))
    )


def tool_result_status(message: SessionItem) -> str | None:
    return optional_text(message.content_payload.get("status"))


def kind_label(message: Any) -> str:
    value = getattr(message, "kind", "")
    enum_value = getattr(value, "value", None)
    if enum_value is not None:
        if enum_value in {"user_message", "assistant_message", "tool_call"}:
            return "message"
        return str(enum_value)
    return str(value)


def message_estimate(message: SessionItem, content: str) -> ContextEstimate:
    base = text_estimate(content or message_preview(message))
    block_types = set(content_block_types(message))
    return ContextEstimate(
        text_chars=base.text_chars,
        text_tokens=base.text_tokens,
        image_count=1 if block_types & {IMAGE_BLOCK_TYPE, IMAGE_REF_BLOCK_TYPE} else 0,
        file_count=1 if block_types & {FILE_BLOCK_TYPE, FILE_REF_BLOCK_TYPE} else 0,
    )


def items_estimate(
    messages: tuple[SessionItem, ...],
    *,
    current_run_id: str | None = None,
) -> ContextEstimate:
    total = ContextEstimate()
    for message in messages:
        content = (
            ""
            if _is_current_inbound_message(message, current_run_id=current_run_id)
            else message_prompt_content(message)
        )
        total = total.plus(message_estimate(message, content))
    return total


def _tool_result_message_preview(message: SessionItem) -> str:
    payload = message.content_payload
    tool_name = optional_text(message.metadata.get("tool_name")) or optional_text(
        payload.get("tool_name"),
    )
    tool_call_id = optional_text(message.metadata.get("tool_call_id")) or optional_text(
        payload.get("tool_call_id"),
    )
    status = optional_text(payload.get("status"))
    content = blocks_prompt_content(content_blocks_from_payload(payload))
    parts = ["tool_result"]
    if tool_name is not None:
        parts.append(tool_name)
    if status is not None:
        parts.append(f"status={status}")
    if tool_call_id is not None:
        parts.append(f"call_id={tool_call_id}")
    digest = _short_digest(content)
    if digest is not None:
        parts.append(f"content_sha256={digest}")
    return truncate("; ".join(parts), 320)


def _function_call_prompt_content(message: SessionItem) -> str:
    payload = message.content_payload
    tool_call_id = optional_text(message.metadata.get("tool_call_id")) or optional_text(
        payload.get("call_id"),
    )
    tool_name = optional_text(message.metadata.get("tool_name")) or optional_text(
        payload.get("name"),
    )
    lines = ["tool_call:"]
    if tool_name is not None:
        lines.append(f"  name: {tool_name}")
    if tool_call_id is not None:
        lines.append(f"  call_id: {tool_call_id}")
    arguments = payload.get("arguments")
    if arguments is not None:
        lines.append(f"  arguments: {json_fragment(arguments)}")
    return "\n".join(lines)


def _tool_result_prompt_content(message: SessionItem) -> str:
    payload = message.content_payload
    tool_call_id = optional_text(message.metadata.get("tool_call_id")) or optional_text(
        payload.get("tool_call_id"),
    )
    tool_name = optional_text(message.metadata.get("tool_name")) or optional_text(
        payload.get("tool_name"),
    )
    status = optional_text(payload.get("status"))
    lines = ["tool_result:"]
    if tool_name is not None:
        lines.append(f"  tool_name: {tool_name}")
    if tool_call_id is not None:
        lines.append(f"  tool_call_id: {tool_call_id}")
    if status is not None:
        lines.append(f"  status: {status}")
    error = payload.get("error")
    if error is not None:
        lines.append(f"  error: {json_fragment(error)}")
    content = blocks_prompt_content(content_blocks_from_payload(payload))
    if content:
        lines.append(f"  content_sha256: {_short_digest(content)}")
        lines.append(f"  content_chars: {len(content)}")
    return "\n".join(lines)


def _is_current_inbound_message(
    message: SessionItem,
    *,
    current_run_id: str | None,
) -> bool:
    if current_run_id is None:
        return False
    return (
        message.role == "user"
        and message.source_kind == "orchestration_run"
        and message.source_id == current_run_id
    )


def _short_digest(value: str) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
