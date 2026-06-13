from __future__ import annotations

import json
from dataclasses import dataclass, field, replace

from crxzipple.modules.llm.domain import LlmMessage, LlmMessageRole
from crxzipple.modules.orchestration.application.prompting import estimate_text_tokens
from crxzipple.modules.session.domain import SessionItem, SessionItemKind
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
    budget: dict[str, object] = field(default_factory=dict)


def build_model_visible_session_item_prompt_window(
    items: tuple[SessionItem, ...],
    *,
    max_chars: int | None = None,
    include_non_protocol_history: bool = True,
) -> PromptTranscript:
    visible_items = tuple(item for item in items if item.visibility.model_visible)
    input_items = (
        visible_items
        if include_non_protocol_history
        else _filter_current_protocol_items(visible_items)
    )
    filtered_items = _truncate_items_to_recent_budget(
        input_items,
        max_chars=max_chars,
    )
    llm_messages = tuple(_item_to_llm_message(item) for item in filtered_items)
    return PromptTranscript(
        messages=llm_messages,
        message_count=len(llm_messages),
        chars=sum(_message_content_chars(message.content) for message in llm_messages),
        estimated_tokens=sum(
            _message_content_tokens(message.content)
            for message in llm_messages
        ),
        tool_result_stats=_tool_result_item_stats(filtered_items),
        budget=_session_item_budget_report(
            input_items,
            filtered_items,
            max_chars=max_chars,
        ),
    )


def _filter_current_protocol_items(
    items: tuple[SessionItem, ...],
) -> tuple[SessionItem, ...]:
    if not items:
        return ()
    current_session_id = items[-1].session_id
    current_user_items = tuple(
        item
        for item in items
        if item.session_id == current_session_id
        and item.kind is SessionItemKind.USER_MESSAGE
        and item.role == "user"
    )
    current_user_item = current_user_items[-1:] if current_user_items else ()
    current_turn_start_sequence = (
        current_user_item[0].sequence_no if current_user_item else -1
    )
    tool_results_by_call_id = {
        item.call_id: item
        for item in items
        if item.session_id == current_session_id
        and item.sequence_no >= current_turn_start_sequence
        and item.kind is SessionItemKind.TOOL_RESULT
        and item.call_id is not None
    }
    paired_protocol_items: list[SessionItem] = []
    for item in items:
        if (
            item.session_id != current_session_id
            or item.sequence_no < current_turn_start_sequence
            or item.kind is not SessionItemKind.TOOL_CALL
            or item.call_id is None
        ):
            continue
        result = tool_results_by_call_id.get(item.call_id)
        if result is None:
            continue
        paired_protocol_items.extend((item, result))
    provider_external_items = tuple(
        item
        for item in items
        if item.session_id == current_session_id
        and item.sequence_no >= current_turn_start_sequence
        and item.kind is SessionItemKind.PROVIDER_EXTERNAL_ITEM
    )
    ordered = (
        *current_user_item,
        *paired_protocol_items,
        *provider_external_items,
    )
    seen: set[str] = set()
    deduped: list[SessionItem] = []
    for item in ordered:
        if item.id in seen:
            continue
        seen.add(item.id)
        deduped.append(item)
    return tuple(sorted(deduped, key=lambda item: item.sequence_no))


def _item_to_llm_message(item: SessionItem) -> LlmMessage:
    role = _item_role(item)
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
        content=_extract_item_content(item, role=role),
        name=tool_name if role is LlmMessageRole.TOOL else None,
        tool_call_id=(
            item.call_id
            if item.kind in {SessionItemKind.TOOL_CALL, SessionItemKind.TOOL_RESULT}
            else None
        ),
        metadata=metadata,
    )


def _item_role(item: SessionItem) -> LlmMessageRole:
    if item.role is not None:
        try:
            return LlmMessageRole(item.role)
        except ValueError:
            pass
    if item.kind is SessionItemKind.TOOL_RESULT:
        return LlmMessageRole.TOOL
    return LlmMessageRole.ASSISTANT


def _extract_item_content(
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
        compact_result = _compact_tool_result_payload(item.content_payload)
        if compact_result is not None:
            return compact_result
        blocks = content_blocks_from_payload(item.content_payload)
        if blocks:
            return blocks
        content = item.content_payload.get("content")
        if isinstance(content, list):
            return content
        if "error" in item.content_payload:
            return [text_content_block(describe_content_for_text_fallback(item.content_payload["error"]))]
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


def _compact_tool_result_payload(
    payload: dict[str, object],
) -> list[dict[str, object]] | None:
    metadata = payload.get("metadata")
    details = payload.get("details")
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


def _tool_result_item_stats(items: tuple[SessionItem, ...]) -> dict[str, object]:
    stats: dict[str, object] = {
        "tool_result_item_count": 0,
        "compacted_result_count": 0,
        "omitted_chars": 0,
        "omitted_count": 0,
        "artifact_ref_count": 0,
        "read_handle_count": 0,
    }
    artifact_refs: set[str] = set()
    for item in items:
        if item.kind is not SessionItemKind.TOOL_RESULT:
            continue
        stats["tool_result_item_count"] = int(stats["tool_result_item_count"]) + 1
        metadata = item.content_payload.get("metadata")
        details = item.content_payload.get("details")
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


def _truncate_items_to_recent_budget(
    items: tuple[SessionItem, ...],
    *,
    max_chars: int | None,
) -> tuple[SessionItem, ...]:
    if max_chars is None or max_chars <= 0:
        return items
    kept: list[tuple[int, SessionItem]] = []
    remaining_chars = max_chars
    for index, item in reversed(tuple(enumerate(items))):
        item_chars = _session_item_content_chars(item)
        if (
            not _is_protocol_required_item(item)
            and not kept
            and item_chars > remaining_chars
        ):
            item = _truncate_item_to_recent_chars(item, remaining_chars)
            item_chars = _session_item_content_chars(item)
        if (
            not _is_protocol_required_item(item)
            and kept
            and item_chars > remaining_chars
        ):
            continue
        kept.append((index, item))
        remaining_chars = max(0, remaining_chars - item_chars)
    kept.sort(key=lambda entry: entry[0])
    return tuple(item for _, item in kept)


def _session_item_budget_report(
    all_items: tuple[SessionItem, ...],
    kept_items: tuple[SessionItem, ...],
    *,
    max_chars: int | None,
) -> dict[str, object]:
    kept_ids = {item.id for item in kept_items}
    dropped_items = tuple(item for item in all_items if item.id not in kept_ids)
    protocol_items = tuple(item for item in all_items if _is_protocol_required_item(item))
    kept_protocol_ids = {item.id for item in kept_items if _is_protocol_required_item(item)}
    report: dict[str, object] = {
        "source": "session_items",
        "budget_unit": "chars",
        "max_chars": max_chars,
        "input_item_count": len(all_items),
        "included_item_count": len(kept_items),
        "collapsed_item_count": len(dropped_items),
        "truncated": bool(dropped_items),
        "frontier": _session_item_frontier(kept_items),
        "included_refs": [_session_item_budget_ref(item) for item in kept_items],
        "collapsed_refs": [_session_item_budget_ref(item) for item in dropped_items],
        "protocol_required_refs": [
            _session_item_budget_ref(item) for item in protocol_items
        ],
        "protocol_required_preserved": all(
            item.id in kept_protocol_ids for item in protocol_items
        ),
    }
    return {key: value for key, value in report.items() if value not in (None, [], {})}


def _session_item_frontier(
    items: tuple[SessionItem, ...],
) -> dict[str, object]:
    if not items:
        return {}
    return {
        "from_sequence_no": min(item.sequence_no for item in items),
        "to_sequence_no": max(item.sequence_no for item in items),
        "from_item_id": items[0].id,
        "to_item_id": items[-1].id,
        "item_count": len(items),
    }


def _session_item_budget_ref(item: SessionItem) -> dict[str, object]:
    ref: dict[str, object] = {
        "owner_module": "session",
        "owner_kind": "session_item",
        "owner_id": item.id,
        "item_id": item.id,
        "session_id": item.session_id,
        "sequence_no": item.sequence_no,
        "kind": item.kind.value,
        "role": item.role or "",
        "render_mode": "full",
        "visibility": "model_visible",
    }
    if item.source_module:
        ref["source_module"] = item.source_module
    if item.source_kind:
        ref["source_kind"] = item.source_kind
    if item.source_id:
        ref["source_id"] = item.source_id
    if item.provider_item_id:
        ref["provider_item_id"] = item.provider_item_id
    if item.provider_item_type:
        ref["provider_item_type"] = item.provider_item_type
    if item.call_id:
        ref["tool_call_id"] = item.call_id
    if item.tool_name:
        ref["tool_name"] = item.tool_name
    if _is_protocol_required_item(item):
        ref["protocol_required"] = True
        ref["budget_class"] = "protocol_required"
    return ref


def _is_protocol_required_item(item: SessionItem) -> bool:
    return item.kind in {
        SessionItemKind.TOOL_CALL,
        SessionItemKind.TOOL_RESULT,
        SessionItemKind.PROVIDER_EXTERNAL_ITEM,
    }


def _session_item_content_chars(item: SessionItem) -> int:
    return _message_content_chars(_extract_item_content(item, role=_item_role(item)))


def _truncate_item_to_recent_chars(
    item: SessionItem,
    max_chars: int,
) -> SessionItem:
    if max_chars <= 0:
        return item
    if _is_protocol_required_item(item):
        return item
    blocks = content_blocks_from_payload(item.content_payload)
    text_content = extract_text_content(blocks if blocks else item.content_payload)
    if text_content is None:
        fallback_text = describe_content_for_text_fallback(item.content_payload)
        truncated_text = fallback_text[-max_chars:]
        return replace(
            item,
            content_payload={
                "blocks": [text_content_block(truncated_text)],
                "text": truncated_text,
            },
        )
    truncated_text = text_content[-max_chars:]
    payload = dict(item.content_payload)
    payload["blocks"] = [text_content_block(truncated_text)]
    payload["text"] = truncated_text
    return replace(item, content_payload=payload)
