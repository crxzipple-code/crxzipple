from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

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
    assistant_progress_message_ids = _unique_summary_ids(
        items,
        "assistant_progress_message_ids",
    )
    tool_call_message_ids = _unique_summary_ids(items, "tool_call_message_ids")
    llm_text_tool_call_steps = _llm_text_tool_call_steps(items)
    llm_tool_only_steps = _llm_tool_only_steps(items)
    tool_only_streaks = _llm_tool_only_streaks(steps, items)
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
        "tool_only_loop_suspected": tool_only_streaks["max"] >= 3,
        "assistant_progress_message_count": len(assistant_progress_message_ids),
        "tool_call_message_count": len(tool_call_message_ids),
        "assistant_progress_message_ids": assistant_progress_message_ids,
        "tool_call_message_ids": tool_call_message_ids,
        "progress_without_tool_call_messages": (
            llm_text_tool_call_steps > 0 and not tool_call_message_ids
        ),
        "repeated_target_count": _optional_int(
            repeated_probe.get("repeated_count"),
            fallback=len(_as_list(repeated_probe.get("repeated"))),
        ),
        "first_endpoint_discovery_step": first_candidate_step,
        "first_candidate_validation_step": first_validation_step,
        "candidate_discovery_to_validation_delta": (
            first_validation_step - first_candidate_step
            if first_candidate_step is not None and first_validation_step is not None
            else None
        ),
        "completed_cancelled_failed": _terminal_status(getattr(run, "status", "")),
        "final_answer_has_verified_facts": final_signal["has_verified_facts"],
        "final_answer_has_gaps": final_signal["has_gaps"],
        "metrics_missing": _missing_metrics(
            first_candidate_step=first_candidate_step,
            first_validation_step=first_validation_step,
            final_signal=final_signal,
            llm_text_tool_call_steps=llm_text_tool_call_steps,
            assistant_progress_message_ids=assistant_progress_message_ids,
            tool_call_message_ids=tool_call_message_ids,
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


def _llm_text_tool_call_steps(items: tuple[Any, ...]) -> int:
    count = 0
    for item in items:
        if _enum_value(getattr(item, "kind", "")) != ExecutionStepItemKind.LLM_INVOCATION.value:
            continue
        payload = _summary_payload(item)
        has_tool_call = bool(_summary_list(payload, "tool_call_names"))
        has_progress = bool(_summary_list(payload, "assistant_progress_message_ids")) or bool(
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
        has_progress = bool(_summary_list(payload, "assistant_progress_message_ids")) or bool(
            _optional_text(payload.get("assistant_progress_text")),
        )
        if has_tool_call and not has_progress:
            count += 1
    return count


def _llm_tool_only_streaks(
    steps: tuple[Any, ...],
    items: tuple[Any, ...],
) -> dict[str, int]:
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
    for item in llm_items:
        payload = _summary_payload(item)
        has_tool_call = bool(_summary_list(payload, "tool_call_names"))
        has_progress = bool(_summary_list(payload, "assistant_progress_message_ids")) or bool(
            _optional_text(payload.get("assistant_progress_text")),
        )
        if has_tool_call and not has_progress:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
            continue
        current_streak = 0
    return {"max": max_streak, "current": current_streak}


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


def _final_answer_signal(result_payload: object) -> dict[str, object]:
    if not isinstance(result_payload, dict):
        return {"has_verified_facts": None, "has_gaps": None}
    return {
        "has_verified_facts": _has_any_key(
            result_payload,
            {"verified_facts", "facts", "evidence", "sources"},
        ),
        "has_gaps": _has_any_key(
            result_payload,
            {"gaps", "unresolved_gaps", "remaining_gaps", "limitations"},
        ),
    }


def _has_any_key(value: object, keys: set[str]) -> bool:
    return _contains_key(value, keys)


def _missing_metrics(
    *,
    first_candidate_step: int | None,
    first_validation_step: int | None,
    final_signal: dict[str, object],
    llm_text_tool_call_steps: int,
    assistant_progress_message_ids: list[str],
    tool_call_message_ids: list[str],
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
    if llm_text_tool_call_steps > 0 and not assistant_progress_message_ids:
        missing.append("assistant_progress_message_ids")
    if llm_text_tool_call_steps > 0 and not tool_call_message_ids:
        missing.append("tool_call_message_ids")
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
