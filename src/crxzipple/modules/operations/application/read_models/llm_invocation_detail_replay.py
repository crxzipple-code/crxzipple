from __future__ import annotations

from collections import Counter

from crxzipple.modules.llm.domain import LlmInvocation
from crxzipple.modules.operations.application.read_models.llm_invocation_detail_common import (
    bounded_text,
    int_value,
    text,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_facts import (
    request_metadata,
)


def request_render_snapshot_label(invocation: LlmInvocation) -> str:
    value = text(request_metadata(invocation).get("request_render_snapshot_id"))
    if value is not None:
        return value
    return "-"


def draft_input_sequence_label(invocation: LlmInvocation) -> str:
    sequence_range = request_metadata(invocation).get("draft_input_sequence_range")
    if not isinstance(sequence_range, dict):
        return "-"
    sessions = sequence_range.get("sessions")
    if not isinstance(sessions, list) or not sessions:
        return "-"
    labels: list[str] = []
    for item in sessions[:3]:
        if not isinstance(item, dict):
            continue
        session_id = text(item.get("session_id")) or "session"
        from_sequence = text(item.get("from_sequence_no")) or "?"
        to_sequence = text(item.get("to_sequence_no")) or "?"
        item_count = text(item.get("item_count")) or "?"
        labels.append(f"{session_id}:{from_sequence}-{to_sequence} ({item_count})")
    if not labels:
        return "-"
    if len(sessions) > 3:
        labels.append(f"+{len(sessions) - 3}")
    return ", ".join(labels)


def tool_result_stat_label(invocation: LlmInvocation, key: str) -> str:
    value = _tool_result_stat_int(invocation, key)
    return str(value) if value else "-"


def tool_result_omitted_label(invocation: LlmInvocation) -> str:
    omitted_count = _tool_result_stat_int(invocation, "omitted_count")
    omitted_chars = _tool_result_stat_int(invocation, "omitted_chars")
    parts: list[str] = []
    if omitted_count:
        parts.append(f"count={omitted_count}")
    if omitted_chars:
        parts.append(f"chars={omitted_chars}")
    return "; ".join(parts) if parts else "-"


def tool_result_refs_label(invocation: LlmInvocation) -> str:
    artifact_ref_count = _tool_result_stat_int(invocation, "artifact_ref_count")
    read_handle_count = _tool_result_stat_int(invocation, "read_handle_count")
    parts: list[str] = []
    if artifact_ref_count:
        parts.append(f"artifact_refs={artifact_ref_count}")
    if read_handle_count:
        parts.append(f"read_handles={read_handle_count}")
    return "; ".join(parts) if parts else "-"


def tool_result_excerpt_count_label(invocation: LlmInvocation) -> str:
    count = _tool_result_excerpt_count(invocation)
    return str(count) if count else "-"


def tool_result_excerpt_sample_label(invocation: LlmInvocation) -> str:
    for item in invocation.input_items:
        if item.kind.value != "function_call_output":
            continue
        if not _input_item_payload_has_tool_result_excerpt(item.payload):
            continue
        output_text = _input_item_output_text(item.payload.get("output"))
        if output_text.strip():
            return bounded_text(output_text.strip().replace("\n", " "), limit=160)
    return "-"


def replay_input_item_count_label(invocation: LlmInvocation) -> str:
    return str(len(invocation.input_items))


def replay_input_item_kinds_label(invocation: LlmInvocation) -> str:
    if not invocation.input_items:
        return "-"
    values = [item.kind.value for item in invocation.input_items[:8]]
    suffix = "..." if len(invocation.input_items) > 8 else ""
    return ", ".join(values) + suffix


def replay_input_item_sources_label(invocation: LlmInvocation) -> str:
    if not invocation.input_items:
        return "-"
    values = tuple(
        dict.fromkeys(
            item.source.strip() or "-"
            for item in invocation.input_items
        ),
    )
    suffix = "..." if len(values) > 8 else ""
    return ", ".join(values[:8]) + suffix


def replay_protocol_items_label(invocation: LlmInvocation) -> str:
    counts = Counter(item.kind.value for item in invocation.input_items)
    if not counts:
        return "-"
    return (
        f"reasoning={counts.get('reasoning', 0)}; "
        f"calls={counts.get('function_call', 0)}; "
        f"outputs={counts.get('function_call_output', 0)}; "
        f"provider_external={counts.get('provider_external_item', 0)}"
    )


def _draft_input_budget_summary(invocation: LlmInvocation) -> dict[str, object]:
    value = request_metadata(invocation).get("draft_input_budget_summary")
    return value if isinstance(value, dict) else {}


def _tool_result_stats(invocation: LlmInvocation) -> dict[str, object]:
    value = _draft_input_budget_summary(invocation).get("tool_result_stats")
    return value if isinstance(value, dict) else {}


def _tool_result_stat_int(invocation: LlmInvocation, key: str) -> int:
    return int_value(_tool_result_stats(invocation).get(key))


def _tool_result_excerpt_count(invocation: LlmInvocation) -> int:
    count = 0
    for item in invocation.input_items:
        if item.kind.value != "function_call_output":
            continue
        if _input_item_payload_has_tool_result_excerpt(item.payload):
            count += 1
    return count


def _input_item_payload_has_tool_result_excerpt(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    output = payload.get("output")
    output_text = _input_item_output_text(output)
    if not output_text:
        return False
    return any(
        token in output_text
        for token in (
            "tool_result:",
            "stdout_excerpt:",
            "stderr_excerpt:",
            "body_excerpt_policy:",
            "artifact_refs:",
            "read_handles:",
        )
    )


def _input_item_output_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for block in value:
            if isinstance(block, dict):
                block_text = block.get("text")
                if isinstance(block_text, str):
                    parts.append(block_text)
        return "\n".join(parts)
    if isinstance(value, dict):
        output_text = value.get("text")
        return output_text if isinstance(output_text, str) else ""
    return ""
