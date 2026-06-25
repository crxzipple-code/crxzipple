from __future__ import annotations

from dataclasses import dataclass, field

from crxzipple.modules.llm.domain import (
    LlmInputItem,
    LlmInputItemKind,
    LlmMessage,
    LlmMessageRole,
)
from crxzipple.modules.llm.application.session_runtime_budget import (
    session_item_budget_report,
    truncate_items_to_recent_budget,
)
from crxzipple.modules.llm.application.session_runtime_item_metrics import (
    message_content_chars,
    message_content_tokens,
)
from crxzipple.modules.llm.application.session_runtime_items import (
    dedupe_adjacent_assistant_progress,
    has_replayable_content,
    is_current_turn_progress_item,
    item_to_llm_input_item,
    item_to_llm_message,
)
from crxzipple.modules.llm.application.session_runtime_tool_result_stats import (
    tool_result_item_stats,
)
from crxzipple.modules.session.domain import (
    SessionItem,
    SessionItemKind,
)
from crxzipple.shared.content_blocks import (
    normalize_content_blocks,
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
        filtered_items = truncate_items_to_recent_budget(
            input_items,
            max_chars=max_chars,
        )
        llm_messages = tuple(item_to_llm_message(item) for item in filtered_items)
        llm_input_items = tuple(
            item_to_llm_input_item(item, message=message)
            for item, message in zip(filtered_items, llm_messages, strict=True)
        )
        return RuntimeTranscript(
            messages=llm_messages,
            input_items=llm_input_items,
            report=RuntimeTranscriptReport(
                message_count=len(llm_messages),
                chars=sum(
                    message_content_chars(message.content) for message in llm_messages
                ),
                estimated_tokens=sum(
                    message_content_tokens(message.content)
                    for message in llm_messages
                ),
                tool_result_stats=tool_result_item_stats(filtered_items),
                budget=session_item_budget_report(
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
    chars = message_content_chars(message.content)
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
            estimated_tokens=message_content_tokens(message.content),
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
        and is_current_turn_progress_item(item)
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
        } and not has_replayable_content(item):
            continue
        if item.kind in {SessionItemKind.TOOL_CALL, SessionItemKind.TOOL_RESULT}:
            if item.id not in kept_protocol_item_ids:
                continue
        normalized.append(item)
    return dedupe_adjacent_assistant_progress(tuple(normalized))
