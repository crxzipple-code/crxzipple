"""Draft input and transcript budget metadata helpers."""

from __future__ import annotations

from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
    RuntimeLlmRequestDraft,
)

from ._metadata import metadata_text
from .snapshot_metadata_values import (
    llm_message_content_chars,
    metadata_dict_list,
    metadata_int_value,
)


def draft_input_chars(draft: RuntimeLlmRequestDraft) -> int:
    return sum(llm_message_content_chars(message.content) for message in draft.messages)


def draft_input_session_item_refs(
    draft: RuntimeLlmRequestDraft,
) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    for message in draft.messages:
        metadata = message.metadata
        item_id = metadata_text(metadata.get("session_item_id"))
        session_id = metadata_text(metadata.get("session_id"))
        sequence_no = metadata_int_value(metadata.get("sequence_no"))
        if item_id is None or session_id is None or sequence_no is None:
            continue
        ref: dict[str, object] = {
            "owner_module": "session",
            "owner_kind": "session_item",
            "owner_id": item_id,
            "item_id": item_id,
            "session_id": session_id,
            "sequence_no": sequence_no,
            "role": message.role.value,
            "render_mode": "full",
            "render_scope": "provider_replay",
        }
        for key in (
            "kind",
            "phase",
            "source_module",
            "source_kind",
            "source_id",
            "provider_item_id",
            "provider_item_type",
            "tool_call_id",
            "tool_name",
            "tool_status",
        ):
            value = metadata_text(metadata.get(key))
            if value is not None:
                ref[key] = value
        refs.append(ref)
    return refs


def merged_protocol_required_refs(
    draft_refs: list[dict[str, object]],
    transcript_budget: dict[str, object],
) -> list[dict[str, object]]:
    refs = [
        *protocol_required_refs(draft_refs),
        *metadata_dict_list(transcript_budget.get("protocol_required_refs")),
    ]
    deduped: list[dict[str, object]] = []
    seen: set[tuple[object, object, object, object, object]] = set()
    for ref in refs:
        identity = (
            ref.get("owner_module"),
            ref.get("owner_kind"),
            ref.get("owner_id"),
            ref.get("item_id"),
            ref.get("tool_call_id"),
        )
        if identity in seen:
            continue
        seen.add(identity)
        payload = dict(ref)
        payload["protocol_required"] = True
        payload["budget_class"] = "protocol_required"
        deduped.append(payload)
    return deduped


def draft_transcript_budget(draft: RuntimeLlmRequestDraft) -> dict[str, object]:
    if draft.report is None:
        return draft_input_session_item_budget(draft)
    report_payload = draft.report.to_payload()
    transcript = report_payload.get("transcript")
    if not isinstance(transcript, dict):
        return draft_input_session_item_budget(draft)
    budget = transcript.get("budget")
    if not isinstance(budget, dict):
        return draft_input_session_item_budget(draft)
    normalized = dict(budget)
    if normalized:
        return normalized
    return draft_input_session_item_budget(draft)


def draft_input_session_item_budget(
    draft: RuntimeLlmRequestDraft,
) -> dict[str, object]:
    draft_refs = draft_input_session_item_refs(draft)
    if not draft_refs:
        return {}
    return {
        "source": "session_items",
        "budget_unit": "chars",
        "input_item_count": len(draft_refs),
        "included_item_count": len(draft_refs),
        "collapsed_item_count": 0,
        "truncated": False,
        "frontier": session_item_frontier(draft_refs),
        "included_refs": draft_refs,
        "protocol_required_refs": protocol_required_refs(draft_refs),
        "protocol_required_preserved": True,
    }


def session_item_frontier(
    refs: list[dict[str, object]],
) -> dict[str, object]:
    sequence_numbers = [
        ref.get("sequence_no") for ref in refs if isinstance(ref.get("sequence_no"), int)
    ]
    if not sequence_numbers:
        return {}
    payload: dict[str, object] = {
        "from_sequence_no": min(sequence_numbers),
        "to_sequence_no": max(sequence_numbers),
        "item_count": len(sequence_numbers),
    }
    first_id = refs[0].get("item_id")
    last_id = refs[-1].get("item_id")
    if isinstance(first_id, str):
        payload["from_item_id"] = first_id
    if isinstance(last_id, str):
        payload["to_item_id"] = last_id
    return payload


def protocol_required_refs(
    refs: list[dict[str, object]],
) -> list[dict[str, object]]:
    required: list[dict[str, object]] = []
    for ref in refs:
        kind = metadata_text(ref.get("kind"))
        if kind not in {
            "agent_progress",
            "tool_call",
            "tool_result",
            "provider_external_item",
        }:
            continue
        payload = dict(ref)
        payload["protocol_required"] = True
        payload["budget_class"] = "protocol_required"
        required.append(payload)
    return required
