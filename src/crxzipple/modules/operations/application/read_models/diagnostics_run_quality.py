from __future__ import annotations

from crxzipple.modules.operations.application.read_models.diagnostics_common import (
    has_any_key,
    joined_text_values,
    optional_int,
    optional_text,
)


def final_answer_signal(result_payload: object) -> dict[str, object]:
    if not isinstance(result_payload, dict):
        return {
            "has_verified_facts": None,
            "has_gaps": None,
            "has_unavailable_evidence": None,
        }
    text = optional_text(result_payload.get("output_text")) or ""
    payload_text = joined_text_values(result_payload)
    return {
        "has_verified_facts": has_any_key(
            result_payload,
            {"verified_facts", "facts", "evidence", "sources"},
        )
        or any(marker in payload_text for marker in ("已确认", "confirmed", "observed")),
        "has_gaps": has_any_key(
            result_payload,
            {"gaps", "unresolved_gaps", "remaining_gaps", "limitations"},
        )
        or any(marker in payload_text for marker in ("无法", "没法", "blocked", "风控", "拦")),
        "has_unavailable_evidence": any(
            marker in text
            for marker in ("无法", "没法", "blocked", "WAF", "风控", "拦住")
        )
        or any(
            marker in payload_text
            for marker in ("无法", "没法", "blocked", "WAF", "风控", "拦住")
        ),
    }


def missing_metrics(
    *,
    first_candidate_step: int | None,
    first_validation_step: int | None,
    final_signal: dict[str, object],
    llm_text_tool_call_steps: int,
    response_item_metrics: dict[str, object],
    assistant_progress_item_ids: list[str],
    tool_call_session_item_ids: list[str],
) -> list[str]:
    missing: list[str] = []
    if first_candidate_step is None:
        missing.append("first_endpoint_discovery_step")
    if first_validation_step is None:
        missing.append("first_candidate_validation_step")
    if final_signal["has_verified_facts"] is None:
        missing.append("final_answer_has_verified_facts")
    if final_signal["has_gaps"] is None:
        missing.append("final_answer_has_gaps")
    response_item_count = optional_int(
        response_item_metrics.get("response_item_count"),
        fallback=0,
    )
    tool_call_response_item_count = optional_int(
        response_item_metrics.get("tool_call_item_count"),
        fallback=0,
    )
    progress_response_item_count = optional_int(
        response_item_metrics.get("reasoning_text_item_count"),
        fallback=0,
    ) + optional_int(
        response_item_metrics.get("assistant_message_item_count"),
        fallback=0,
    )
    has_response_item_truth = response_item_count > 0
    has_progress_truth = bool(assistant_progress_item_ids) or progress_response_item_count > 0
    has_tool_call_truth = bool(tool_call_session_item_ids) or tool_call_response_item_count > 0
    if llm_text_tool_call_steps > 0 and not has_progress_truth:
        missing.append("assistant_progress_item_ids")
    if (
        llm_text_tool_call_steps > 0
        and not has_tool_call_truth
        and not has_response_item_truth
    ):
        missing.append("tool_call_session_item_ids")
    return missing
