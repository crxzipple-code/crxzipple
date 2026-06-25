from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.diagnostics_common import (
    enum_value,
    optional_int,
    optional_text,
    summary_list,
    summary_payload,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    ExecutionStepItemKind,
)

TOOL_ONLY_STREAK_WARNING_THRESHOLD = 3
VALIDATION_DELTA_WARNING_THRESHOLD = 8


def llm_tool_only_streaks(
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
            if enum_value(getattr(item, "kind", ""))
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
            payload = summary_payload(item)
            has_tool_call = bool(summary_list(payload, "tool_call_names"))
            has_progress = bool(summary_list(payload, "assistant_progress_item_ids")) or bool(
                optional_text(payload.get("assistant_progress_text")),
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


def loop_health(
    *,
    tool_only_streaks: dict[str, object],
    validation_delta: int | None,
) -> dict[str, object]:
    max_streak = optional_int(tool_only_streaks.get("max"), fallback=0)
    current_streak = optional_int(tool_only_streaks.get("current"), fallback=0)
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
