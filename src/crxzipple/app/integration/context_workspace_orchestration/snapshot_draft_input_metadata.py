"""Draft input metadata for Context Workspace snapshots."""

from __future__ import annotations

from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
    RuntimeLlmRequestDraft,
)

from ._metadata import estimate_text_tokens_from_chars
from .snapshot_draft_budget import (
    draft_input_chars,
    draft_input_session_item_refs,
    draft_transcript_budget,
    merged_protocol_required_refs,
    session_item_frontier,
)
from .snapshot_metadata_values import metadata_dict_list


def build_snapshot_draft_input_metadata(
    draft: RuntimeLlmRequestDraft,
) -> dict[str, object]:
    input_chars = draft_input_chars(draft)
    input_tokens = estimate_text_tokens_from_chars(input_chars)
    session_item_refs = draft_input_session_item_refs(draft)
    input_budget = draft_transcript_budget(draft)
    protocol_required_refs = merged_protocol_required_refs(
        session_item_refs,
        input_budget,
    )
    execution_required_refs = metadata_dict_list(
        input_budget.get("execution_chain_protocol_required_refs"),
    )
    return {
        "draft_input_message_count": len(draft.messages),
        "draft_input_roles": [message.role.value for message in draft.messages],
        "draft_input_chars": input_chars,
        "draft_input_estimated_tokens": input_tokens,
        "draft_input_session_item_refs": session_item_refs,
        "draft_input_session_item_count": len(session_item_refs),
        "draft_input_session_item_frontier": session_item_frontier(session_item_refs),
        "draft_input_budget": input_budget,
        "protocol_required_refs": protocol_required_refs,
        "protocol_required_ref_count": len(protocol_required_refs),
        "execution_chain_protocol_required_refs": execution_required_refs,
        "execution_chain_protocol_required_ref_count": len(execution_required_refs),
    }
