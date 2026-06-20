from __future__ import annotations

import json
from dataclasses import dataclass, field, replace

from crxzipple.modules.llm.domain import (
    LlmInputItem,
    LlmInputItemKind,
    LlmMessage,
    LlmMessageRole,
)
from crxzipple.modules.llm.application.tool_result_model_text import (
    render_tool_result_model_text,
)
from crxzipple.shared.token_estimates import estimate_text_tokens
from crxzipple.modules.session.domain import (
    SessionItem,
    SessionItemKind,
    SessionItemPhase,
)
from crxzipple.modules.tool.application.result_envelope import (
    TOOL_RESULT_ENVELOPE_METADATA_KEY,
)
from crxzipple.shared.content_blocks import (
    content_blocks_from_payload,
    describe_content_for_text_fallback,
    extract_text_content,
    normalize_content_blocks,
    text_content_block,
)


@dataclass(frozen=True, slots=True)
class RuntimeTranscriptReport:
    message_count: int
    chars: int
    estimated_tokens: int
    tool_result_stats: dict[str, object]
    budget: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RuntimeTranscript:
    messages: tuple[LlmMessage, ...]
    input_items: tuple[LlmInputItem, ...] = ()
    report: RuntimeTranscriptReport = field(
        default_factory=lambda: RuntimeTranscriptReport(
            message_count=0,
            chars=0,
            estimated_tokens=0,
            tool_result_stats={},
        ),
    )


@dataclass(frozen=True, slots=True)
class RuntimeReplayWindowBuilder:
    """Build a runtime replay window from session facts."""

    def build_from_session_items(
        self,
        items: tuple[SessionItem, ...],
        *,
        max_chars: int | None = None,
        include_non_protocol_history: bool = True,
    ) -> RuntimeTranscript:
        source_items = tuple(items)
        replay_candidates = (
            source_items
            if include_non_protocol_history
            else _filter_current_protocol_items(source_items)
        )
        input_items = _normalize_tool_protocol_replay_items(replay_candidates)
        filtered_items = _truncate_items_to_recent_budget(
            input_items,
            max_chars=max_chars,
        )
        llm_messages = tuple(_item_to_llm_message(item) for item in filtered_items)
        llm_input_items = tuple(
            _item_to_llm_input_item(item, message=message)
            for item, message in zip(filtered_items, llm_messages, strict=True)
        )
        return RuntimeTranscript(
            messages=llm_messages,
            input_items=llm_input_items,
            report=RuntimeTranscriptReport(
                message_count=len(llm_messages),
                chars=sum(
                    _message_content_chars(message.content) for message in llm_messages
                ),
                estimated_tokens=sum(
                    _message_content_tokens(message.content)
                    for message in llm_messages
                ),
                tool_result_stats=_tool_result_item_stats(filtered_items),
                budget=_session_item_budget_report(
                    input_items,
                    filtered_items,
                    max_chars=max_chars,
                    source_items=source_items,
                ),
            ),
        )


def build_session_fact_runtime_window(
    items: tuple[SessionItem, ...],
    *,
    max_chars: int | None = None,
    include_non_protocol_history: bool = True,
) -> RuntimeTranscript:
    return RuntimeReplayWindowBuilder().build_from_session_items(
        items,
        max_chars=max_chars,
        include_non_protocol_history=include_non_protocol_history,
    )


def build_current_inbound_runtime_transcript(
    content: object,
    *,
    source: str,
    source_id: str,
) -> RuntimeTranscript:
    blocks = normalize_content_blocks(content)
    if not blocks:
        return RuntimeTranscript(
            messages=(),
            report=RuntimeTranscriptReport(
                message_count=0,
                chars=0,
                estimated_tokens=0,
                tool_result_stats={},
            ),
        )
    message = LlmMessage(
        role=LlmMessageRole.USER,
        content=blocks,
        metadata={
            "runtime_request_block_kind": "current_inbound",
            "source": source,
            "source_kind": "orchestration_run",
            "source_id": source_id,
        },
    )
    chars = _message_content_chars(message.content)
    return RuntimeTranscript(
        messages=(message,),
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={
                    "role": message.role.value,
                    "content": message.content,
                },
                source="current_inbound",
                metadata=dict(message.metadata),
            ),
        ),
        report=RuntimeTranscriptReport(
            message_count=1,
            chars=chars,
            estimated_tokens=_message_content_tokens(message.content),
            tool_result_stats={},
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
        and item.kind is SessionItemKind.TOOL_RESULT
        and item.call_id is not None
        and item.sequence_no >= current_turn_start_sequence
    }
    paired_protocol_items: list[SessionItem] = []
    for item in items:
        if (
            item.session_id != current_session_id
            or item.kind is not SessionItemKind.TOOL_CALL
            or item.call_id is None
            or item.sequence_no < current_turn_start_sequence
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
        and item.kind is SessionItemKind.PROVIDER_EXTERNAL_ACTIVITY
    )
    current_progress_items = tuple(
        item
        for item in items
        if item.session_id == current_session_id
        and item.sequence_no >= current_turn_start_sequence
        and _is_current_turn_progress_item(item)
    )
    ordered = (
        *current_user_item,
        *current_progress_items,
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


def _normalize_tool_protocol_replay_items(
    items: tuple[SessionItem, ...],
) -> tuple[SessionItem, ...]:
    if not items:
        return ()
    tool_calls_by_id: dict[str, list[SessionItem]] = {}
    tool_results_by_id: dict[str, list[SessionItem]] = {}
    for item in items:
        if item.call_id is None or not item.call_id.strip():
            continue
        if item.kind is SessionItemKind.TOOL_CALL:
            tool_calls_by_id.setdefault(item.call_id, []).append(item)
        elif item.kind is SessionItemKind.TOOL_RESULT:
            tool_results_by_id.setdefault(item.call_id, []).append(item)
    kept_protocol_item_ids: set[str] = set()
    for call_id, calls in tool_calls_by_id.items():
        ordered_calls = sorted(calls, key=lambda item: item.sequence_no)
        ordered_results = sorted(
            tool_results_by_id.get(call_id, []),
            key=lambda item: item.sequence_no,
        )
        selected_pair = next(
            (
                (call, result)
                for call in ordered_calls
                for result in ordered_results
                if result.sequence_no > call.sequence_no
            ),
            None,
        )
        if selected_pair is None:
            continue
        call, result = selected_pair
        kept_protocol_item_ids.add(call.id)
        kept_protocol_item_ids.add(result.id)
    normalized: list[SessionItem] = []
    for item in items:
        if item.kind in {
            SessionItemKind.REASONING,
            SessionItemKind.ASSISTANT_MESSAGE,
            SessionItemKind.USER_MESSAGE,
        } and not _has_replayable_content(item):
            continue
        if item.kind in {SessionItemKind.TOOL_CALL, SessionItemKind.TOOL_RESULT}:
            if item.id not in kept_protocol_item_ids:
                continue
        normalized.append(item)
    return _dedupe_adjacent_assistant_progress(tuple(normalized))


def _is_current_turn_progress_item(item: SessionItem) -> bool:
    if item.kind is SessionItemKind.REASONING:
        return _has_replayable_content(item)
    if (
        item.kind is SessionItemKind.ASSISTANT_MESSAGE
        and item.role == "assistant"
        and item.phase is not SessionItemPhase.FINAL_ANSWER
    ):
        return _has_replayable_content(item)
    return False


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


def _item_to_llm_input_item(
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


def _has_replayable_content(item: SessionItem) -> bool:
    blocks = content_blocks_from_payload(item.content_payload)
    text_content = extract_text_content(blocks if blocks else item.content_payload)
    if text_content is not None and text_content.strip():
        return True
    if blocks:
        return True
    text = item.content_payload.get("text")
    return isinstance(text, str) and bool(text.strip())


def _dedupe_adjacent_assistant_progress(
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
            text = _session_item_text_fingerprint(item)
            if text is not None and text == previous_progress_text:
                continue
            previous_progress_text = text
        else:
            previous_progress_text = None
        deduped.append(item)
    return tuple(deduped)


def _session_item_text_fingerprint(item: SessionItem) -> str | None:
    blocks = content_blocks_from_payload(item.content_payload)
    text_content = extract_text_content(blocks if blocks else item.content_payload)
    if text_content is not None and text_content.strip():
        return text_content.strip()
    text = item.content_payload.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return None


def _compact_tool_result_payload(
    payload: dict[str, object],
) -> list[dict[str, object]] | None:
    content = render_tool_result_model_text(payload)
    if content is None:
        return None
    return [text_content_block(content)]


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


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


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
    source_items: tuple[SessionItem, ...] | None = None,
) -> dict[str, object]:
    source_items = all_items if source_items is None else source_items
    kept_ids = {item.id for item in kept_items}
    dropped_items = tuple(item for item in all_items if item.id not in kept_ids)
    original_items_by_id = {item.id: item for item in all_items}
    shortened_items = tuple(
        item
        for item in kept_items
        if item.id in original_items_by_id
        and _session_item_content_chars(item)
        < _session_item_content_chars(original_items_by_id[item.id])
    )
    collapsed_chars = sum(_session_item_content_chars(item) for item in dropped_items)
    shortened_chars = sum(
        _session_item_content_chars(original_items_by_id[item.id])
        - _session_item_content_chars(item)
        for item in shortened_items
        if item.id in original_items_by_id
    )
    protocol_items = tuple(item for item in all_items if _is_protocol_required_item(item))
    kept_protocol_ids = {item.id for item in kept_items if _is_protocol_required_item(item)}
    source_protocol_diagnostics = _tool_protocol_diagnostics(source_items)
    protocol_diagnostics = _tool_protocol_diagnostics(kept_items)
    normalization_diagnostics = _tool_protocol_normalization_diagnostics(
        source_protocol_diagnostics,
        protocol_diagnostics,
    )
    report: dict[str, object] = {
        "source": "session_items",
        "budget_unit": "chars",
        "max_chars": max_chars,
        "input_item_count": len(all_items),
        "included_item_count": len(kept_items),
        "collapsed_item_count": len(dropped_items),
        "shortened_item_count": len(shortened_items),
        "collapsed_chars": collapsed_chars,
        "shortened_chars": shortened_chars,
        "omitted_chars": collapsed_chars + shortened_chars,
        "truncated": bool(dropped_items or shortened_items),
        "frontier": _session_item_frontier(kept_items),
        "included_refs": [_session_item_budget_ref(item) for item in kept_items],
        "collapsed_refs": [_session_item_budget_ref(item) for item in dropped_items],
        "shortened_refs": [_session_item_budget_ref(item) for item in shortened_items],
        "protocol_required_refs": [
            _session_item_budget_ref(item) for item in protocol_items
        ],
        "protocol_required_preserved": all(
            item.id in kept_protocol_ids for item in protocol_items
        ),
        "source_tool_protocol_diagnostics": source_protocol_diagnostics,
        "tool_protocol_diagnostics": protocol_diagnostics,
        "tool_protocol_normalization": normalization_diagnostics,
        "orphan_tool_output_count": protocol_diagnostics.get(
            "orphan_tool_output_count",
        ),
        "missing_tool_output_count": protocol_diagnostics.get(
            "missing_tool_output_count",
        ),
        "duplicate_tool_call_id_count": protocol_diagnostics.get(
            "duplicate_tool_call_id_count",
        ),
    }
    return {key: value for key, value in report.items() if value not in (None, [], {})}


def _tool_protocol_normalization_diagnostics(
    source: dict[str, object],
    replay: dict[str, object],
) -> dict[str, object]:
    source_orphans = _int_value(source.get("orphan_tool_output_count"))
    replay_orphans = _int_value(replay.get("orphan_tool_output_count"))
    source_missing = _int_value(source.get("missing_tool_output_count"))
    replay_missing = _int_value(replay.get("missing_tool_output_count"))
    source_duplicate_calls = _int_value(source.get("duplicate_tool_call_id_count"))
    replay_duplicate_calls = _int_value(replay.get("duplicate_tool_call_id_count"))
    source_duplicate_outputs = _int_value(source.get("duplicate_tool_output_id_count"))
    replay_duplicate_outputs = _int_value(replay.get("duplicate_tool_output_id_count"))
    diagnostics: dict[str, object] = {
        "schema_version": "2026-06-15.tool_protocol_normalization.v1",
        "dropped_orphan_tool_output_count": max(0, source_orphans - replay_orphans),
        "dropped_missing_tool_output_count": max(0, source_missing - replay_missing),
        "dropped_duplicate_tool_call_id_count": max(
            0,
            source_duplicate_calls - replay_duplicate_calls,
        ),
        "dropped_duplicate_tool_output_id_count": max(
            0,
            source_duplicate_outputs - replay_duplicate_outputs,
        ),
        "source_had_protocol_breaks": any(
            count > 0
            for count in (
                source_orphans,
                source_missing,
                source_duplicate_calls,
                source_duplicate_outputs,
            )
        ),
        "replay_has_protocol_breaks": any(
            count > 0
            for count in (
                replay_orphans,
                replay_missing,
                replay_duplicate_calls,
                replay_duplicate_outputs,
            )
        ),
    }
    return {
        key: value
        for key, value in diagnostics.items()
        if value not in (None, [], {}, 0, False)
        or key
        in {
            "dropped_orphan_tool_output_count",
            "dropped_missing_tool_output_count",
            "dropped_duplicate_tool_call_id_count",
            "dropped_duplicate_tool_output_id_count",
            "source_had_protocol_breaks",
            "replay_has_protocol_breaks",
        }
    }


def _tool_protocol_diagnostics(items: tuple[SessionItem, ...]) -> dict[str, object]:
    calls_by_id: dict[str, list[SessionItem]] = {}
    outputs_by_id: dict[str, list[SessionItem]] = {}
    orphan_outputs: list[SessionItem] = []
    for item in items:
        if item.kind is SessionItemKind.TOOL_CALL:
            if item.call_id is None or not item.call_id.strip():
                continue
            calls_by_id.setdefault(item.call_id, []).append(item)
            continue
        if item.kind is not SessionItemKind.TOOL_RESULT:
            continue
        if item.call_id is None or not item.call_id.strip():
            orphan_outputs.append(item)
            continue
        outputs_by_id.setdefault(item.call_id, []).append(item)
    for call_id, outputs in outputs_by_id.items():
        calls = calls_by_id.get(call_id, [])
        if not calls:
            orphan_outputs.extend(outputs)
            continue
        first_call_sequence = min(item.sequence_no for item in calls)
        orphan_outputs.extend(
            item for item in outputs if item.sequence_no < first_call_sequence
        )
    missing_output_calls = tuple(
        calls[0]
        for call_id, calls in calls_by_id.items()
        if call_id not in outputs_by_id
    )
    duplicate_call_ids = tuple(
        call_id for call_id, calls in calls_by_id.items() if len(calls) > 1
    )
    duplicate_output_ids = tuple(
        call_id for call_id, outputs in outputs_by_id.items() if len(outputs) > 1
    )
    diagnostics: dict[str, object] = {
        "schema_version": "2026-06-15.tool_protocol_diagnostics.v1",
        "tool_call_count": sum(len(call_items) for call_items in calls_by_id.values()),
        "tool_output_count": sum(
            len(output_items) for output_items in outputs_by_id.values()
        )
        + len(
            tuple(
                item
                for item in orphan_outputs
                if item.call_id is None or not item.call_id.strip()
            ),
        ),
        "orphan_tool_output_count": len(orphan_outputs),
        "missing_tool_output_count": len(missing_output_calls),
        "duplicate_tool_call_id_count": len(duplicate_call_ids),
        "duplicate_tool_output_id_count": len(duplicate_output_ids),
        "orphan_tool_outputs": [
            _session_item_budget_ref(item) for item in tuple(orphan_outputs)[:12]
        ],
        "missing_tool_outputs": [
            _session_item_budget_ref(item) for item in missing_output_calls[:12]
        ],
        "duplicate_tool_call_ids": list(duplicate_call_ids[:12]),
        "duplicate_tool_output_ids": list(duplicate_output_ids[:12]),
    }
    return {
        key: value
        for key, value in diagnostics.items()
        if value not in (None, [], {}, 0)
        or key
        in {
            "tool_call_count",
            "tool_output_count",
            "orphan_tool_output_count",
            "missing_tool_output_count",
            "duplicate_tool_call_id_count",
            "duplicate_tool_output_id_count",
        }
    }


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
        "render_scope": "provider_replay",
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
        SessionItemKind.PROVIDER_EXTERNAL_ACTIVITY,
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
    return replace(
        item,
        content_payload=payload,
    )
