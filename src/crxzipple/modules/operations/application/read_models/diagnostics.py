from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from crxzipple.modules.operations.application.read_models.diagnostics_common import (
    as_list,
    enum_value,
    optional_int,
)
from crxzipple.modules.operations.application.read_models.diagnostics_loop_health import (
    llm_tool_only_streaks,
    loop_health,
)
from crxzipple.modules.operations.application.read_models.diagnostics_response_metrics import (
    request_input_metrics,
    response_item_metrics,
)
from crxzipple.modules.operations.application.read_models.diagnostics_run_quality import (
    final_answer_signal,
    missing_metrics,
)
from crxzipple.modules.operations.application.read_models.diagnostics_run_signals import (
    first_step_index,
    kind_count,
    looks_like_candidate_discovery,
    looks_like_candidate_validation,
    repeated_probe_observation,
    terminal_status,
    tool_call_count,
    tool_result_contract_counts,
    ui_step_count,
    unique_summary_ids,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    ExecutionStepItemKind,
)


class LoopRegressionQuery(Protocol):
    def get_run(self, run_id: str) -> Any:
        ...

    def list_execution_chains(self, turn_id: str) -> list[Any]:
        ...

    def list_execution_steps(self, chain_id: str) -> list[Any]:
        ...

    def list_execution_step_items(self, step_id: str) -> list[Any]:
        ...


def build_loop_regression_baseline(
    query: LoopRegressionQuery,
    *,
    run_id: str,
    task_label: str | None = None,
    response_item_resolver: Callable[[str], Any | None] | None = None,
) -> dict[str, object]:
    run = query.get_run(run_id)
    chains = tuple(query.list_execution_chains(run_id))
    steps = tuple(
        step
        for chain in chains
        for step in query.list_execution_steps(str(getattr(chain, "id", "")))
    )
    items = tuple(
        item
        for step in steps
        for item in query.list_execution_step_items(str(getattr(step, "id", "")))
    )
    repeated_probe = repeated_probe_observation(getattr(run, "metadata", {}))
    first_candidate_step = first_step_index(
        steps,
        items,
        predicate=looks_like_candidate_discovery,
    )
    first_validation_step = first_step_index(
        steps,
        items,
        predicate=looks_like_candidate_validation,
    )
    final_signal = final_answer_signal(getattr(run, "result_payload", None))
    assistant_progress_item_ids = unique_summary_ids(
        items,
        "assistant_progress_item_ids",
    )
    tool_call_session_item_ids = unique_summary_ids(
        items,
        "tool_call_session_item_ids",
    )
    tool_result_contract = tool_result_contract_counts(items)
    response_metrics = response_item_metrics(items, response_item_resolver)
    request_metrics = request_input_metrics(items)
    llm_text_tool_call_steps = int(response_metrics["llm_text_tool_call_steps"])
    llm_tool_only_steps = int(response_metrics["llm_tool_only_steps"])
    tool_only_streaks = llm_tool_only_streaks(
        steps,
        items,
        response_metrics["shape_by_llm_item_id"],
    )
    validation_delta = (
        first_validation_step - first_candidate_step
        if first_candidate_step is not None and first_validation_step is not None
        else None
    )
    health = loop_health(
        tool_only_streaks=tool_only_streaks,
        validation_delta=validation_delta,
    )
    baseline: dict[str, object] = {
        "task": task_label or "",
        "run_id": run_id,
        "status": enum_value(getattr(run, "status", "")),
        "orchestration_steps": len(steps),
        "ui_steps": ui_step_count(items),
        "llm_calls": kind_count(items, ExecutionStepItemKind.LLM_INVOCATION),
        "tool_calls": tool_call_count(items),
        "llm_text_tool_call_steps": llm_text_tool_call_steps,
        "llm_tool_only_steps": llm_tool_only_steps,
        "max_consecutive_llm_tool_only_steps": tool_only_streaks["max"],
        "current_consecutive_llm_tool_only_steps": tool_only_streaks["current"],
        "tool_only_loop_suspected": bool(health["tool_only_loop_suspected"]),
        "loop_health": health,
        "llm_response_item_count": response_metrics["response_item_count"],
        "llm_reasoning_response_item_count": response_metrics["reasoning_item_count"],
        "llm_reasoning_text_item_count": response_metrics["reasoning_text_item_count"],
        "llm_assistant_message_response_item_count": response_metrics[
            "assistant_message_item_count"
        ],
        "llm_tool_call_response_item_count": response_metrics["tool_call_item_count"],
        "llm_response_item_missing_count": response_metrics["missing_item_count"],
        "llm_request_input_mode_counts": request_metrics["input_mode_counts"],
        "llm_request_input_missing_count": request_metrics["missing_count"],
        "llm_request_input_item_count": request_metrics["input_item_count"],
        "llm_runtime_transcript_steps": request_metrics["runtime_transcript_steps"],
        "llm_runtime_transcript_item_count": request_metrics[
            "runtime_transcript_item_count"
        ],
        "assistant_progress_item_count": len(assistant_progress_item_ids),
        "tool_call_session_item_count": len(tool_call_session_item_ids),
        "assistant_progress_item_ids": assistant_progress_item_ids,
        "tool_call_session_item_ids": tool_call_session_item_ids,
        "progress_without_tool_call_items": (
            llm_text_tool_call_steps > 0 and not tool_call_session_item_ids
        ),
        "tool_result_items": tool_result_contract["items"],
        "tool_result_summary_count": tool_result_contract["summary_count"],
        "tool_result_exit_code_count": tool_result_contract["exit_code_count"],
        "tool_result_read_handle_count": tool_result_contract["read_handle_count"],
        "tool_result_truncated_count": tool_result_contract["truncated_count"],
        "repeated_target_count": optional_int(
            repeated_probe.get("repeated_count"),
            fallback=len(as_list(repeated_probe.get("repeated"))),
        ),
        "first_endpoint_discovery_step": first_candidate_step,
        "first_candidate_validation_step": first_validation_step,
        "candidate_discovery_to_validation_delta": validation_delta,
        "completed_cancelled_failed": terminal_status(getattr(run, "status", "")),
        "final_answer_has_verified_facts": final_signal["has_verified_facts"],
        "final_answer_has_gaps": final_signal["has_gaps"],
        "final_answer_has_unavailable_evidence": final_signal[
            "has_unavailable_evidence"
        ],
        "metrics_missing": missing_metrics(
            first_candidate_step=first_candidate_step,
            first_validation_step=first_validation_step,
            final_signal=final_signal,
            llm_text_tool_call_steps=llm_text_tool_call_steps,
            response_item_metrics=response_metrics,
            assistant_progress_item_ids=assistant_progress_item_ids,
            tool_call_session_item_ids=tool_call_session_item_ids,
        ),
    }
    if repeated_probe:
        baseline["repeated_probe_observation"] = repeated_probe
    return baseline


__all__ = ["build_loop_regression_baseline"]
