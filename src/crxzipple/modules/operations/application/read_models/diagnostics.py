from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, Protocol

from crxzipple.modules.orchestration.domain.value_objects import (
    ExecutionStepItemKind,
)

TOOL_ONLY_STREAK_WARNING_THRESHOLD = 3
VALIDATION_DELTA_WARNING_THRESHOLD = 8


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
    repeated_probe = _repeated_probe_observation(getattr(run, "metadata", {}))
    first_candidate_step = _first_step_index(
        steps,
        items,
        predicate=_looks_like_candidate_discovery,
    )
    first_validation_step = _first_step_index(
        steps,
        items,
        predicate=_looks_like_candidate_validation,
    )
    final_signal = _final_answer_signal(getattr(run, "result_payload", None))
    assistant_progress_item_ids = _unique_summary_ids(
        items,
        "assistant_progress_item_ids",
    )
    tool_call_session_item_ids = _unique_summary_ids(
        items,
        "tool_call_session_item_ids",
    )
    tool_result_contract = _tool_result_contract_counts(items)
    response_item_metrics = _response_item_metrics(items, response_item_resolver)
    request_input_metrics = _request_input_metrics(items)
    llm_text_tool_call_steps = int(response_item_metrics["llm_text_tool_call_steps"])
    llm_tool_only_steps = int(response_item_metrics["llm_tool_only_steps"])
    tool_only_streaks = _llm_tool_only_streaks(
        steps,
        items,
        response_item_metrics["shape_by_llm_item_id"],
    )
    validation_delta = (
        first_validation_step - first_candidate_step
        if first_candidate_step is not None and first_validation_step is not None
        else None
    )
    loop_health = _loop_health(
        tool_only_streaks=tool_only_streaks,
        validation_delta=validation_delta,
    )
    baseline: dict[str, object] = {
        "task": task_label or "",
        "run_id": run_id,
        "status": _enum_value(getattr(run, "status", "")),
        "orchestration_steps": len(steps),
        "ui_steps": _ui_step_count(items),
        "llm_calls": _kind_count(items, ExecutionStepItemKind.LLM_INVOCATION),
        "tool_calls": _tool_call_count(items),
        "llm_text_tool_call_steps": llm_text_tool_call_steps,
        "llm_tool_only_steps": llm_tool_only_steps,
        "max_consecutive_llm_tool_only_steps": tool_only_streaks["max"],
        "current_consecutive_llm_tool_only_steps": tool_only_streaks["current"],
        "tool_only_loop_suspected": bool(loop_health["tool_only_loop_suspected"]),
        "loop_health": loop_health,
        "llm_response_item_count": response_item_metrics["response_item_count"],
        "llm_reasoning_response_item_count": response_item_metrics[
            "reasoning_item_count"
        ],
        "llm_reasoning_text_item_count": response_item_metrics[
            "reasoning_text_item_count"
        ],
        "llm_assistant_message_response_item_count": response_item_metrics[
            "assistant_message_item_count"
        ],
        "llm_tool_call_response_item_count": response_item_metrics[
            "tool_call_item_count"
        ],
        "llm_response_item_missing_count": response_item_metrics[
            "missing_item_count"
        ],
        "llm_request_input_mode_counts": request_input_metrics["input_mode_counts"],
        "llm_request_input_missing_count": request_input_metrics["missing_count"],
        "llm_request_input_item_count": request_input_metrics["input_item_count"],
        "llm_runtime_transcript_steps": request_input_metrics[
            "runtime_transcript_steps"
        ],
        "llm_runtime_transcript_item_count": request_input_metrics[
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
        "repeated_target_count": _optional_int(
            repeated_probe.get("repeated_count"),
            fallback=len(_as_list(repeated_probe.get("repeated"))),
        ),
        "first_endpoint_discovery_step": first_candidate_step,
        "first_candidate_validation_step": first_validation_step,
        "candidate_discovery_to_validation_delta": validation_delta,
        "completed_cancelled_failed": _terminal_status(getattr(run, "status", "")),
        "final_answer_has_verified_facts": final_signal["has_verified_facts"],
        "final_answer_has_gaps": final_signal["has_gaps"],
        "final_answer_has_unavailable_evidence": final_signal[
            "has_unavailable_evidence"
        ],
        "metrics_missing": _missing_metrics(
            first_candidate_step=first_candidate_step,
            first_validation_step=first_validation_step,
            final_signal=final_signal,
            llm_text_tool_call_steps=llm_text_tool_call_steps,
            response_item_metrics=response_item_metrics,
            assistant_progress_item_ids=assistant_progress_item_ids,
            tool_call_session_item_ids=tool_call_session_item_ids,
        ),
    }
    if repeated_probe:
        baseline["repeated_probe_observation"] = repeated_probe
    return baseline


def _kind_count(items: Iterable[Any], kind: ExecutionStepItemKind) -> int:
    return sum(1 for item in items if _enum_value(getattr(item, "kind", "")) == kind.value)


def _tool_call_count(items: tuple[Any, ...]) -> int:
    explicit = _kind_count(items, ExecutionStepItemKind.TOOL_CALL)
    if explicit:
        return explicit
    return _kind_count(items, ExecutionStepItemKind.TOOL_RUN)


def _response_item_metrics(
    items: tuple[Any, ...],
    response_item_resolver: Callable[[str], Any | None] | None,
) -> dict[str, object]:
    response_item_cache: dict[str, Any | None] = {}
    response_item_count = 0
    missing_item_count = 0
    reasoning_item_count = 0
    reasoning_text_item_count = 0
    assistant_message_item_count = 0
    tool_call_item_count = 0
    llm_text_tool_call_steps = 0
    llm_tool_only_steps = 0
    shape_by_llm_item_id: dict[str, dict[str, bool]] = {}
    for item in items:
        if (
            _enum_value(getattr(item, "kind", ""))
            != ExecutionStepItemKind.LLM_INVOCATION.value
        ):
            continue
        item_id = str(getattr(item, "id", ""))
        payload = _summary_payload(item)
        response_item_ids = [
            text
            for raw_id in _summary_list(payload, "llm_response_item_ids")
            if (text := _optional_text(raw_id)) is not None
        ]
        resolved_items = [
            resolved
            for resolved in (
                _resolve_response_item(
                    item_id,
                    resolver=response_item_resolver,
                    cache=response_item_cache,
                )
                for item_id in response_item_ids
            )
            if resolved is not None
        ]
        missing_item_count += max(0, len(response_item_ids) - len(resolved_items))
        if resolved_items:
            response_item_count += len(resolved_items)
            has_tool_call = any(
                _response_item_kind(response_item) == "tool_call"
                for response_item in resolved_items
            )
            has_progress = any(
                _response_item_is_provider_replay_progress(response_item)
                for response_item in resolved_items
            )
            for response_item in resolved_items:
                kind = _response_item_kind(response_item)
                if kind == "reasoning":
                    reasoning_item_count += 1
                    if _response_item_has_text(response_item):
                        reasoning_text_item_count += 1
                elif kind == "assistant_message":
                    assistant_message_item_count += 1
                elif kind == "tool_call":
                    tool_call_item_count += 1
        else:
            has_tool_call = bool(_summary_list(payload, "tool_call_names"))
            has_progress = bool(
                _summary_list(payload, "assistant_progress_item_ids"),
            ) or bool(_optional_text(payload.get("assistant_progress_text")))
        if has_tool_call and has_progress:
            llm_text_tool_call_steps += 1
        if has_tool_call and not has_progress:
            llm_tool_only_steps += 1
        if item_id:
            shape_by_llm_item_id[item_id] = {
                "has_tool_call": has_tool_call,
                "has_progress": has_progress,
            }
    return {
        "response_item_count": response_item_count,
        "missing_item_count": missing_item_count,
        "reasoning_item_count": reasoning_item_count,
        "reasoning_text_item_count": reasoning_text_item_count,
        "assistant_message_item_count": assistant_message_item_count,
        "tool_call_item_count": tool_call_item_count,
        "llm_text_tool_call_steps": llm_text_tool_call_steps,
        "llm_tool_only_steps": llm_tool_only_steps,
        "shape_by_llm_item_id": shape_by_llm_item_id,
    }


def _request_input_metrics(items: tuple[Any, ...]) -> dict[str, object]:
    input_mode_counts: dict[str, int] = {}
    missing_count = 0
    input_item_count = 0
    runtime_transcript_item_count = 0
    for item in items:
        if (
            _enum_value(getattr(item, "kind", ""))
            != ExecutionStepItemKind.LLM_INVOCATION.value
        ):
            continue
        payload = _summary_payload(item)
        request_input = payload.get("llm_request_input")
        if not isinstance(request_input, dict):
            missing_count += 1
            continue
        input_mode = _optional_text(request_input.get("input_mode")) or "unknown"
        input_mode_counts[input_mode] = input_mode_counts.get(input_mode, 0) + 1
        input_item_count += _optional_int(request_input.get("input_item_count"))
        if input_mode == "runtime_transcript":
            runtime_transcript_item_count += _optional_int(
                request_input.get("input_item_count"),
            )
    return {
        "input_mode_counts": input_mode_counts,
        "runtime_transcript_steps": input_mode_counts.get("runtime_transcript", 0),
        "missing_count": missing_count,
        "input_item_count": input_item_count,
        "runtime_transcript_item_count": runtime_transcript_item_count,
    }


def _resolve_response_item(
    item_id: str,
    *,
    resolver: Callable[[str], Any | None] | None,
    cache: dict[str, Any | None],
) -> Any | None:
    if item_id in cache:
        return cache[item_id]
    if resolver is None:
        cache[item_id] = None
        return None
    try:
        cache[item_id] = resolver(item_id)
    except Exception:
        cache[item_id] = None
    return cache[item_id]


def _response_item_kind(response_item: Any) -> str:
    return _enum_value(getattr(response_item, "kind", ""))


def _response_item_is_provider_replay_progress(response_item: Any) -> bool:
    kind = _response_item_kind(response_item)
    if kind == "assistant_message":
        return _response_item_has_text(response_item)
    if kind == "reasoning":
        return _response_item_has_text(response_item)
    return False


def _response_item_has_text(response_item: Any) -> bool:
    payload = (
        response_item.to_payload()
        if hasattr(response_item, "to_payload")
        else dict(getattr(response_item, "__dict__", {}))
    )
    return bool(
        _optional_text(payload.get("text"))
        or _optional_text(payload.get("content"))
        or _optional_text(payload.get("summary"))
        or _optional_text(_joined_text_values(payload.get("content_payload"))),
    )


def _llm_text_tool_call_steps(items: tuple[Any, ...]) -> int:
    count = 0
    for item in items:
        if (
            _enum_value(getattr(item, "kind", ""))
            != ExecutionStepItemKind.LLM_INVOCATION.value
        ):
            continue
        payload = _summary_payload(item)
        has_tool_call = bool(_summary_list(payload, "tool_call_names"))
        has_progress = bool(_summary_list(payload, "assistant_progress_item_ids")) or bool(
            _optional_text(payload.get("assistant_progress_text")),
        )
        if has_tool_call and has_progress:
            count += 1
    return count


def _llm_tool_only_steps(items: tuple[Any, ...]) -> int:
    count = 0
    for item in items:
        if _enum_value(getattr(item, "kind", "")) != ExecutionStepItemKind.LLM_INVOCATION.value:
            continue
        payload = _summary_payload(item)
        has_tool_call = bool(_summary_list(payload, "tool_call_names"))
        has_progress = bool(_summary_list(payload, "assistant_progress_item_ids")) or bool(
            _optional_text(payload.get("assistant_progress_text")),
        )
        if has_tool_call and not has_progress:
            count += 1
    return count


def _llm_tool_only_streaks(
    steps: tuple[Any, ...],
    items: tuple[Any, ...],
    shape_by_llm_item_id: object | None = None,
) -> dict[str, object]:
    step_index_by_id = {
        str(getattr(step, "id", "")): int(getattr(step, "step_index", 0) or 0)
        for step in steps
    }
    llm_items = sorted(
        (
            item
            for item in items
            if _enum_value(getattr(item, "kind", ""))
            == ExecutionStepItemKind.LLM_INVOCATION.value
        ),
        key=lambda item: step_index_by_id.get(str(getattr(item, "step_id", "")), 0),
    )
    max_streak = 0
    current_streak = 0
    current_segment: dict[str, object] | None = None
    segments: list[dict[str, object]] = []
    shape_map = shape_by_llm_item_id if isinstance(shape_by_llm_item_id, dict) else {}
    for item in llm_items:
        item_id = str(getattr(item, "id", ""))
        step_id = str(getattr(item, "step_id", ""))
        step_index = step_index_by_id.get(step_id, 0)
        shape = shape_map.get(str(getattr(item, "id", "")))
        if isinstance(shape, dict):
            has_tool_call = shape.get("has_tool_call") is True
            has_progress = shape.get("has_progress") is True
        else:
            payload = _summary_payload(item)
            has_tool_call = bool(_summary_list(payload, "tool_call_names"))
            has_progress = bool(_summary_list(payload, "assistant_progress_item_ids")) or bool(
                _optional_text(payload.get("assistant_progress_text")),
            )
        if has_tool_call and not has_progress:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
            if current_segment is None:
                current_segment = {
                    "start_step_index": step_index,
                    "end_step_index": step_index,
                    "start_llm_item_id": item_id,
                    "end_llm_item_id": item_id,
                    "length": 1,
                }
            else:
                current_segment["end_step_index"] = step_index
                current_segment["end_llm_item_id"] = item_id
                current_segment["length"] = int(current_segment["length"]) + 1
            continue
        if current_segment is not None:
            segments.append(current_segment)
            current_segment = None
        current_streak = 0
    if current_segment is not None:
        segments.append(current_segment)
    return {
        "max": max_streak,
        "current": current_streak,
        "segments": segments,
    }


def _loop_health(
    *,
    tool_only_streaks: dict[str, object],
    validation_delta: int | None,
) -> dict[str, object]:
    max_streak = _optional_int(tool_only_streaks.get("max"), fallback=0)
    current_streak = _optional_int(tool_only_streaks.get("current"), fallback=0)
    warnings: list[str] = []
    if max_streak >= TOOL_ONLY_STREAK_WARNING_THRESHOLD:
        warnings.append("tool_only_streak")
    if (
        validation_delta is not None
        and validation_delta > VALIDATION_DELTA_WARNING_THRESHOLD
    ):
        warnings.append("validation_lag")
    return {
        "tool_only_loop_suspected": max_streak >= TOOL_ONLY_STREAK_WARNING_THRESHOLD,
        "tool_only_streak_warning_threshold": TOOL_ONLY_STREAK_WARNING_THRESHOLD,
        "max_tool_only_streak": max_streak,
        "current_tool_only_streak": current_streak,
        "tool_only_streak_segments": list(
            tool_only_streaks.get("segments")
            if isinstance(tool_only_streaks.get("segments"), list)
            else []
        ),
        "validation_delta": validation_delta,
        "validation_delta_warning_threshold": VALIDATION_DELTA_WARNING_THRESHOLD,
        "validation_lag_suspected": (
            validation_delta is not None
            and validation_delta > VALIDATION_DELTA_WARNING_THRESHOLD
        ),
        "warnings": warnings,
    }


def _unique_summary_ids(items: tuple[Any, ...], key: str) -> list[str]:
    ids: list[str] = []
    for item in items:
        for raw_id in _summary_list(_summary_payload(item), key):
            normalized = _optional_text(raw_id)
            if normalized is not None and normalized not in ids:
                ids.append(normalized)
    return ids


def _summary_list(payload: dict[str, object], key: str) -> tuple[object, ...]:
    value = payload.get(key)
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return ()


def _ui_step_count(items: tuple[Any, ...]) -> int:
    count = 0
    for item in items:
        payload = _summary_payload(item)
        tool_id = _optional_text(payload.get("tool_id")) or ""
        tool_name = _optional_text(payload.get("tool_name")) or ""
        if tool_id.startswith("browser.") or tool_name.startswith("browser."):
            count += 1
    return count


def _first_step_index(
    steps: tuple[Any, ...],
    items: tuple[Any, ...],
    *,
    predicate: Any,
) -> int | None:
    step_index_by_id = {
        str(getattr(step, "id", "")): int(getattr(step, "step_index", 0) or 0)
        for step in steps
    }
    matches = [
        step_index_by_id.get(str(getattr(item, "step_id", "")))
        for item in items
        if predicate(_summary_payload(item))
    ]
    normalized = [value for value in matches if value is not None]
    return min(normalized) if normalized else None


def _looks_like_candidate_discovery(payload: dict[str, object]) -> bool:
    return _contains_key(
        payload,
        {
            "endpoint",
            "api_endpoint",
            "request_url",
            "url",
            "path",
            "file_path",
            "command",
            "candidate",
            "candidates",
            "resource",
            "resource_url",
        },
    )


def _looks_like_candidate_validation(payload: dict[str, object]) -> bool:
    return _contains_key(
        payload,
        {
            "validated",
            "validation",
            "validation_result",
            "verified",
            "verified_fact",
            "evidence",
            "evidence_type",
            "result_shape",
        },
    )


def _contains_key(value: object, keys: set[str]) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key) in keys:
                return True
            if _contains_key(child, keys):
                return True
    if isinstance(value, (list, tuple)):
        return any(_contains_key(item, keys) for item in value)
    return False


def _summary_payload(item: Any) -> dict[str, object]:
    payload = getattr(item, "summary_payload", None)
    return dict(payload) if isinstance(payload, dict) else {}


def _repeated_probe_observation(metadata: object) -> dict[str, object]:
    if not isinstance(metadata, dict):
        return {}
    value = metadata.get("repeated_probe_observation")
    return dict(value) if isinstance(value, dict) else {}


def _tool_result_contract_counts(items: tuple[Any, ...]) -> dict[str, int]:
    result_items = [
        item
        for item in items
        if _enum_value(getattr(item, "kind", ""))
        == ExecutionStepItemKind.TOOL_RESULT.value
    ]
    summary_count = 0
    exit_code_count = 0
    read_handle_count = 0
    truncated_count = 0
    for item in result_items:
        payload = _summary_payload(item)
        if _optional_text(payload.get("result_summary")) or _optional_text(
            payload.get("summary")
        ) or _optional_text(payload.get("tool_result_summary")):
            summary_count += 1
        if _has_key(payload, "exit_code"):
            exit_code_count += 1
        read_handle_count += len(_summary_list(payload, "read_handles"))
        truncated = payload.get("truncated")
        output_truncated = payload.get("output_truncated")
        if truncated is True or output_truncated is True:
            truncated_count += 1
    return {
        "items": len(result_items),
        "summary_count": summary_count,
        "exit_code_count": exit_code_count,
        "read_handle_count": read_handle_count,
        "truncated_count": truncated_count,
    }


def _final_answer_signal(result_payload: object) -> dict[str, object]:
    if not isinstance(result_payload, dict):
        return {
            "has_verified_facts": None,
            "has_gaps": None,
            "has_unavailable_evidence": None,
        }
    text = _optional_text(result_payload.get("output_text")) or ""
    payload_text = _joined_text_values(result_payload)
    return {
        "has_verified_facts": _has_any_key(
            result_payload,
            {"verified_facts", "facts", "evidence", "sources"},
        )
        or any(marker in payload_text for marker in ("已确认", "confirmed", "observed")),
        "has_gaps": _has_any_key(
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


def _has_any_key(value: object, keys: set[str]) -> bool:
    return _contains_key(value, keys)


def _joined_text_values(value: object) -> str:
    if isinstance(value, dict):
        return "\n".join(_joined_text_values(child) for child in value.values())
    if isinstance(value, (list, tuple)):
        return "\n".join(_joined_text_values(child) for child in value)
    text = _optional_text(value)
    return text or ""


def _has_key(value: object, key: str) -> bool:
    return isinstance(value, dict) and key in value


def _missing_metrics(
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
    response_item_count = _optional_int(
        response_item_metrics.get("response_item_count"),
        fallback=0,
    )
    tool_call_response_item_count = _optional_int(
        response_item_metrics.get("tool_call_item_count"),
        fallback=0,
    )
    progress_response_item_count = _optional_int(
        response_item_metrics.get("reasoning_text_item_count"),
        fallback=0,
    ) + _optional_int(
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


def _terminal_status(status: object) -> str:
    value = _enum_value(status)
    if value in {"completed", "cancelled", "failed"}:
        return value
    return "non_terminal"


def _enum_value(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_int(value: object, *, fallback: int = 0) -> int:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return fallback


def _as_list(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


__all__ = ["build_loop_regression_baseline"]
