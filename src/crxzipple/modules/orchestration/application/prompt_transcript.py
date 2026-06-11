from __future__ import annotations

import json
from dataclasses import dataclass, replace

from crxzipple.modules.llm.domain import LlmMessage, LlmMessageRole
from crxzipple.modules.orchestration.application.prompting import estimate_text_tokens
from crxzipple.modules.session.domain import SessionMessage
from crxzipple.modules.tool.application.result_envelope import (
    TOOL_RESULT_ENVELOPE_METADATA_KEY,
)
from crxzipple.shared.content_blocks import (
    content_blocks_from_payload,
    describe_content_for_text_fallback,
    extract_text_content,
    text_content_block,
)


@dataclass(frozen=True, slots=True)
class PromptTranscript:
    messages: tuple[LlmMessage, ...]
    message_count: int
    chars: int
    estimated_tokens: int
    tool_result_stats: dict[str, object]


def build_current_run_prompt_window(
    messages: tuple[SessionMessage, ...],
    *,
    completed_tool_call_ids: tuple[str, ...] | None = None,
    consumed_through_sequence_no: int | None = None,
    preserve_message_ids: tuple[str, ...] = (),
) -> PromptTranscript:
    return _build_session_message_prompt_window(
        messages,
        completed_tool_call_ids=completed_tool_call_ids,
        consumed_through_sequence_no=consumed_through_sequence_no,
        preserve_message_ids=preserve_message_ids,
    )


def build_memory_flush_prompt_transcript(
    messages: tuple[SessionMessage, ...],
    *,
    max_chars: int,
) -> PromptTranscript:
    return _build_session_message_prompt_window(messages, max_chars=max_chars)


def _build_session_message_prompt_window(
    messages: tuple[SessionMessage, ...],
    *,
    max_chars: int | None = None,
    completed_tool_call_ids: tuple[str, ...] | None = None,
    consumed_through_sequence_no: int | None = None,
    preserve_message_ids: tuple[str, ...] = (),
) -> PromptTranscript:
    filtered_messages = _prune_processed_history_attachments(
        _filter_transcript_messages(
            messages,
            completed_tool_call_ids=completed_tool_call_ids,
            consumed_through_sequence_no=consumed_through_sequence_no,
            preserve_message_ids=preserve_message_ids,
        ),
    )
    filtered_messages = _truncate_messages_to_recent_budget(
        filtered_messages,
        max_chars=max_chars,
    )
    tool_result_stats = _tool_result_stats(filtered_messages)
    llm_messages = tuple(_to_llm_message(message) for message in filtered_messages)
    return PromptTranscript(
        messages=llm_messages,
        message_count=len(llm_messages),
        chars=sum(_message_content_chars(message.content) for message in llm_messages),
        estimated_tokens=sum(
            _message_content_tokens(message.content)
            for message in llm_messages
        ),
        tool_result_stats=tool_result_stats,
    )


def _to_llm_message(message: SessionMessage) -> LlmMessage:
    try:
        role = LlmMessageRole(message.role)
    except ValueError:
        role = LlmMessageRole.USER
    tool_call_id = message.metadata.get("tool_call_id")
    if not isinstance(tool_call_id, str) or not tool_call_id.strip():
        tool_call_id = None
    tool_name = message.metadata.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name.strip():
        payload_tool_name = message.content_payload.get("tool_name")
        if isinstance(payload_tool_name, str) and payload_tool_name.strip():
            tool_name = payload_tool_name.strip()
        else:
            tool_name = None
    metadata = {
        "session_message_id": message.id,
        "session_id": message.session_id,
        "sequence_no": message.sequence_no,
        "kind": message.kind.value,
        "source_kind": message.source_kind,
        "source_id": message.source_id,
    }
    if tool_name is not None:
        metadata["tool_name"] = tool_name
    if role is LlmMessageRole.TOOL and "status" in message.content_payload:
        metadata["tool_status"] = message.content_payload["status"]
    if role is LlmMessageRole.TOOL and "error" in message.content_payload:
        metadata["tool_error"] = message.content_payload["error"]
    return LlmMessage(
        role=role,
        content=_extract_content(message, role=role),
        name=tool_name,
        tool_call_id=tool_call_id,
        metadata=metadata,
    )


def _extract_content(
    message: SessionMessage,
    *,
    role: LlmMessageRole,
) -> object:
    if (
        role is LlmMessageRole.ASSISTANT
        and message.content_payload.get("type") == "function_call"
    ):
        return dict(message.content_payload)
    if role is LlmMessageRole.TOOL:
        compact_result = _compact_tool_result_content(message)
        if compact_result is not None:
            return compact_result
        blocks = content_blocks_from_payload(message.content_payload)
        if blocks:
            return blocks
        if "error" in message.content_payload:
            return [text_content_block(describe_content_for_text_fallback(message.content_payload["error"]))]
        return [text_content_block("Tool completed.")]
    blocks = content_blocks_from_payload(message.content_payload)
    if blocks:
        return blocks
    return [
        text_content_block(
            json.dumps(
                message.content_payload,
                ensure_ascii=True,
                sort_keys=True,
            ),
        ),
    ]


def _compact_tool_result_content(message: SessionMessage) -> list[dict[str, object]] | None:
    metadata = message.content_payload.get("metadata")
    details = message.content_payload.get("details")
    if not isinstance(metadata, dict):
        metadata = {}
    if not isinstance(details, dict):
        details = {}
    envelope = metadata.get(TOOL_RESULT_ENVELOPE_METADATA_KEY)
    if isinstance(envelope, dict):
        content = _compact_tool_result_envelope_text(
            envelope,
            artifact_ids=_metadata_artifact_ids(metadata),
            body_removed=details.get("body_removed_from_details") is True,
            browser_evidence=_metadata_browser_evidence(metadata),
        )
        if content is not None:
            return [text_content_block(content)]
    artifact_ids = _metadata_artifact_ids(metadata)
    if not artifact_ids and details.get("body_removed_from_details") is not True:
        return None
    lines = ["result_body: omitted_from_provider_transcript"]
    endpoint = _optional_text(details.get("endpoint"))
    method = _optional_text(details.get("method"))
    if endpoint is not None:
        lines.append(f"endpoint: {endpoint}")
    if method is not None:
        lines.append(f"method: {method}")
    evidence_path = _browser_evidence_path_summary(_metadata_browser_evidence(metadata))
    if evidence_path is not None:
        lines.append(f"evidence_path: {evidence_path}")
    if artifact_ids:
        lines.append(f"artifact_refs: {', '.join(artifact_ids)}")
    lines.append("read_full_result: use owner refs or evidence read_hints")
    return [text_content_block("\n".join(lines))]


def _compact_tool_result_envelope_text(
    envelope: dict[str, object],
    *,
    artifact_ids: tuple[str, ...],
    body_removed: bool,
    browser_evidence: dict[str, object],
) -> str | None:
    if envelope.get("truncated") is not True and not artifact_ids and not body_removed:
        return None
    lines = ["result_body: omitted_from_provider_transcript"]
    status = _optional_text(envelope.get("status"))
    summary = _optional_text(envelope.get("summary"))
    if status is not None:
        lines.append(f"status: {status}")
    if summary is not None:
        lines.append(f"summary: {summary}")
    key_facts = envelope.get("key_facts")
    if isinstance(key_facts, dict) and key_facts:
        lines.append(
            "key_facts: "
            + json.dumps(key_facts, ensure_ascii=True, sort_keys=True),
        )
    evidence_path = _browser_evidence_path_summary(browser_evidence)
    if evidence_path is not None:
        lines.append(f"evidence_path: {evidence_path}")
    refs = _text_list(envelope.get("evidence_refs"))
    if artifact_ids:
        refs = tuple(dict.fromkeys((*refs, *artifact_ids)))
    if refs:
        lines.append(f"artifact_refs: {', '.join(refs)}")
    omitted_count = _optional_int(envelope.get("omitted_count"))
    omitted_chars = _optional_int(envelope.get("omitted_chars"))
    if omitted_count is not None:
        lines.append(f"omitted_count: {omitted_count}")
    if omitted_chars is not None:
        lines.append(f"omitted_chars: {omitted_chars}")
    read_handles = envelope.get("read_handles")
    if isinstance(read_handles, list) and read_handles:
        lines.append(
            "read_handles: "
            + json.dumps(read_handles[:8], ensure_ascii=True, sort_keys=True),
        )
    warnings = _text_list(envelope.get("warnings"))
    if warnings:
        lines.append(f"warnings: {'; '.join(warnings)}")
    lines.append("read_full_result: use owner refs or evidence read_hints")
    return "\n".join(lines)


def _tool_result_stats(messages: tuple[SessionMessage, ...]) -> dict[str, object]:
    stats: dict[str, object] = {
        "tool_result_message_count": 0,
        "compacted_result_count": 0,
        "omitted_chars": 0,
        "omitted_count": 0,
        "artifact_ref_count": 0,
        "read_handle_count": 0,
    }
    artifact_refs: set[str] = set()
    for message in messages:
        if message.role != "tool":
            continue
        stats["tool_result_message_count"] = (
            int(stats["tool_result_message_count"]) + 1
        )
        metadata = message.content_payload.get("metadata")
        details = message.content_payload.get("details")
        if not isinstance(metadata, dict):
            metadata = {}
        if not isinstance(details, dict):
            details = {}
        envelope = metadata.get(TOOL_RESULT_ENVELOPE_METADATA_KEY)
        artifact_ids = _metadata_artifact_ids(metadata)
        for artifact_id in artifact_ids:
            artifact_refs.add(artifact_id)
        if not isinstance(envelope, dict):
            if artifact_ids or details.get("body_removed_from_details") is True:
                stats["compacted_result_count"] = (
                    int(stats["compacted_result_count"]) + 1
                )
            continue
        if (
            envelope.get("truncated") is True
            or artifact_ids
            or details.get("body_removed_from_details") is True
        ):
            stats["compacted_result_count"] = (
                int(stats["compacted_result_count"]) + 1
            )
        stats["omitted_chars"] = int(stats["omitted_chars"]) + (
            _optional_int(envelope.get("omitted_chars")) or 0
        )
        stats["omitted_count"] = int(stats["omitted_count"]) + (
            _optional_int(envelope.get("omitted_count")) or 0
        )
        for artifact_id in _text_list(envelope.get("evidence_refs")):
            artifact_refs.add(artifact_id)
        read_handles = envelope.get("read_handles")
        if isinstance(read_handles, list):
            stats["read_handle_count"] = (
                int(stats["read_handle_count"]) + len(read_handles)
            )
    stats["artifact_ref_count"] = len(artifact_refs)
    return stats


def _metadata_artifact_ids(metadata: dict[str, object]) -> tuple[str, ...]:
    raw = metadata.get("artifact_ids")
    if not isinstance(raw, list):
        raw = metadata.get("browser_artifact_ids")
    if not isinstance(raw, list):
        return ()
    values = [_optional_text(item) for item in raw]
    return tuple(dict.fromkeys(value for value in values if value is not None))


def _metadata_browser_evidence(metadata: dict[str, object]) -> dict[str, object]:
    value = metadata.get("browser_evidence")
    if not isinstance(value, dict):
        return {}
    return dict(value)


def _browser_evidence_path_summary(evidence: dict[str, object]) -> str | None:
    key = _optional_text(evidence.get("evidence_path_key"))
    title = _optional_text(evidence.get("evidence_path_title"))
    tools = _text_list(evidence.get("evidence_path_tools"))
    if key is None and title is None and not tools:
        return None
    label = key or title or "browser_evidence"
    if key is not None and title is not None:
        label = f"{key} ({title})"
    if tools:
        label += ": " + ", ".join(tools[:4])
    return label


def _text_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    values = [_optional_text(item) for item in value]
    return tuple(dict.fromkeys(item for item in values if item is not None))


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _message_content_chars(content: object) -> int:
    text_content = extract_text_content(content)
    if text_content is not None:
        return len(text_content)
    return len(describe_content_for_text_fallback(content))


def _message_content_tokens(content: object) -> int:
    text_content = extract_text_content(content)
    if text_content is not None:
        return estimate_text_tokens(text_content)
    return estimate_text_tokens(describe_content_for_text_fallback(content))


def _filter_transcript_messages(
    messages: tuple[SessionMessage, ...],
    *,
    completed_tool_call_ids: tuple[str, ...] | None = None,
    consumed_through_sequence_no: int | None = None,
    preserve_message_ids: tuple[str, ...] = (),
) -> tuple[SessionMessage, ...]:
    visible_messages = _messages_after_consumed_frontier(
        messages,
        consumed_through_sequence_no=consumed_through_sequence_no,
        preserve_message_ids=preserve_message_ids,
    )
    explicit_completed_tool_call_ids = (
        _normalized_tool_call_ids(completed_tool_call_ids)
        if completed_tool_call_ids is not None
        else None
    )
    visible_completed_tool_call_ids = {
        tool_call_id.strip()
        for message in visible_messages
        if message.role == "tool"
        for tool_call_id in (message.metadata.get("tool_call_id"),)
        if isinstance(tool_call_id, str) and tool_call_id.strip()
    }
    completed_tool_call_id_set = (
        visible_completed_tool_call_ids
        if explicit_completed_tool_call_ids is None
        else explicit_completed_tool_call_ids & visible_completed_tool_call_ids
    )
    filtered: list[SessionMessage] = []
    for message in visible_messages:
        tool_call_id = message.metadata.get("tool_call_id")
        normalized_tool_call_id = (
            tool_call_id.strip()
            if isinstance(tool_call_id, str) and tool_call_id.strip()
            else None
        )
        if (
            explicit_completed_tool_call_ids is not None
            and message.role == "tool"
            and normalized_tool_call_id not in explicit_completed_tool_call_ids
        ):
            continue
        is_function_call = (
            message.role == "assistant"
            and message.content_payload.get("type") == "function_call"
        )
        if not is_function_call:
            filtered.append(message)
            continue
        if normalized_tool_call_id in completed_tool_call_id_set:
            filtered.append(message)
    return tuple(filtered)


def _messages_after_consumed_frontier(
    messages: tuple[SessionMessage, ...],
    *,
    consumed_through_sequence_no: int | None,
    preserve_message_ids: tuple[str, ...],
) -> tuple[SessionMessage, ...]:
    if consumed_through_sequence_no is None:
        return messages
    preserved = {
        value.strip()
        for value in preserve_message_ids
        if isinstance(value, str) and value.strip()
    }
    return tuple(
        message
        for message in messages
        if message.sequence_no > consumed_through_sequence_no or message.id in preserved
    )


def _normalized_tool_call_ids(values: tuple[str, ...] | None) -> set[str]:
    return {
        value.strip()
        for value in values or ()
        if isinstance(value, str) and value.strip()
    }


def _prune_processed_history_attachments(
    messages: tuple[SessionMessage, ...],
) -> tuple[SessionMessage, ...]:
    last_assistant_index = max(
        (
            index
            for index, message in enumerate(messages)
            if message.role == "assistant"
        ),
        default=-1,
    )
    if last_assistant_index <= 0:
        return messages

    pruned: list[SessionMessage] = []
    for index, message in enumerate(messages):
        if index >= last_assistant_index:
            pruned.append(message)
            continue
        blocks = content_blocks_from_payload(message.content_payload)
        if not blocks or all(block.get("type") == "text" for block in blocks):
            pruned.append(message)
            continue
        replacement_blocks = []
        for block in blocks:
            block_type = str(block.get("type") or "").strip()
            if block_type == "text":
                replacement_blocks.append(block)
                continue
            placeholder = "[attachment data removed - already processed by model]"
            if block_type in {"image", "image_ref"}:
                placeholder = "[image data removed - already processed by model]"
            elif block_type in {"file", "file_ref"}:
                placeholder = "[file data removed - already processed by model]"
            replacement_blocks.append(text_content_block(placeholder))
        payload = dict(message.content_payload)
        payload["blocks"] = replacement_blocks
        replacement_text = extract_text_content({"blocks": replacement_blocks})
        if replacement_text is not None:
            payload["text"] = replacement_text
        else:
            payload.pop("text", None)
        pruned.append(replace(message, content_payload=payload))
    return tuple(pruned)


def _truncate_messages_to_recent_budget(
    messages: tuple[SessionMessage, ...],
    *,
    max_chars: int | None,
) -> tuple[SessionMessage, ...]:
    if max_chars is None or max_chars <= 0:
        return messages

    assistant_function_call_indices: dict[str, int] = {}
    for index, message in enumerate(messages):
        if message.role != "assistant":
            continue
        if message.content_payload.get("type") != "function_call":
            continue
        tool_call_id = message.metadata.get("tool_call_id")
        if isinstance(tool_call_id, str) and tool_call_id.strip():
            assistant_function_call_indices[tool_call_id.strip()] = index

    kept: list[tuple[int, SessionMessage]] = []
    kept_indices: set[int] = set()
    required_indices: set[int] = set()
    remaining_chars = max_chars
    cutoff_reached = False

    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        forced = index in required_indices
        if not forced and cutoff_reached:
            continue

        message_chars = _session_message_content_chars(message)
        if not forced and kept and message_chars > remaining_chars:
            cutoff_reached = True
            continue
        if (
            not forced
            and not kept
            and remaining_chars > 0
            and message_chars > remaining_chars
        ):
            message = _truncate_message_to_recent_chars(message, remaining_chars)
            message_chars = _session_message_content_chars(message)
            cutoff_reached = True

        kept.append((index, message))
        kept_indices.add(index)
        remaining_chars = max(0, remaining_chars - message_chars)

        if message.role != "tool":
            continue
        tool_call_id = message.metadata.get("tool_call_id")
        if not isinstance(tool_call_id, str) or not tool_call_id.strip():
            continue
        function_call_index = assistant_function_call_indices.get(tool_call_id.strip())
        if function_call_index is not None and function_call_index not in kept_indices:
            required_indices.add(function_call_index)

    if len(kept) == len(messages):
        return messages
    kept.sort(key=lambda item: item[0])
    return tuple(message for _, message in kept)


def _session_message_content_chars(message: SessionMessage) -> int:
    try:
        role = LlmMessageRole(message.role)
    except ValueError:
        role = LlmMessageRole.USER
    return _message_content_chars(_extract_content(message, role=role))


def _truncate_message_to_recent_chars(
    message: SessionMessage,
    max_chars: int,
) -> SessionMessage:
    if max_chars <= 0:
        return message
    if message.role == "assistant" and message.content_payload.get("type") == "function_call":
        return message
    blocks = content_blocks_from_payload(message.content_payload)
    text_content = extract_text_content(blocks if blocks else message.content_payload)
    if text_content is None:
        fallback_text = describe_content_for_text_fallback(message.content_payload)
        truncated_text = fallback_text[-max_chars:]
        return replace(
            message,
            content_payload={
                "blocks": [text_content_block(truncated_text)],
                "text": truncated_text,
            },
        )
    truncated_text = text_content[-max_chars:]
    payload = dict(message.content_payload)
    payload["blocks"] = [text_content_block(truncated_text)]
    payload["text"] = truncated_text
    return replace(message, content_payload=payload)
