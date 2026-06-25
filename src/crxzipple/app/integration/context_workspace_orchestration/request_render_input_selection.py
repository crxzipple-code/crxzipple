"""Request-render input ref selection from an LLM draft."""

from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
    RuntimeLlmRequestDraft,
)

from .request_render_refs import (
    merge_current_inbound_budget_refs,
    request_input_refs,
    request_session_item_max_chars,
    snapshot_ref_tuple,
)
from .snapshot_draft_budget import (
    draft_input_session_item_refs,
    draft_transcript_budget,
    merged_protocol_required_refs,
)


@dataclass(frozen=True)
class RequestRenderInputSelection:
    draft_input_budget: dict[str, object]
    draft_input_session_item_refs: list[dict[str, object]]
    control_protocol_required_refs: tuple[dict[str, object], ...]
    protocol_required_refs: tuple[dict[str, object], ...]
    request_input_item_refs: tuple[dict[str, object], ...]
    execution_required_refs: tuple[dict[str, object], ...]
    session_item_max_chars: int | None


def build_request_render_input_selection(
    draft: RuntimeLlmRequestDraft,
    *,
    run_id: str,
) -> RequestRenderInputSelection:
    budget = draft_transcript_budget(draft)
    base_session_item_refs = draft_input_session_item_refs(draft)
    control_protocol_required_refs = tuple(
        merged_protocol_required_refs(
            base_session_item_refs,
            budget,
        ),
    )
    request_session_item_refs = merge_current_inbound_budget_refs(
        base_session_item_refs,
        budget,
        run_id=run_id,
    )
    protocol_required_refs = tuple(
        merged_protocol_required_refs(
            request_session_item_refs,
            budget,
        ),
    )
    input_item_refs = (
        request_input_refs(
            request_session_item_refs,
            protocol_required_refs,
            run_id=run_id,
        )
        if request_session_item_refs
        else ()
    )
    return RequestRenderInputSelection(
        draft_input_budget=budget,
        draft_input_session_item_refs=request_session_item_refs,
        control_protocol_required_refs=control_protocol_required_refs,
        protocol_required_refs=protocol_required_refs,
        request_input_item_refs=input_item_refs,
        execution_required_refs=snapshot_ref_tuple(
            budget.get("execution_chain_protocol_required_refs"),
        ),
        session_item_max_chars=request_session_item_max_chars(draft),
    )
