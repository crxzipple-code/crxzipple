from __future__ import annotations

from crxzipple.modules.orchestration.domain import ExecutionStep, ExecutionStepItem


def continuation_decision_items(
    items: list[ExecutionStepItem],
) -> list[ExecutionStepItem]:
    return [
        item
        for item in items
        if item.kind.value == "continuation_decision"
    ]


def latest_continuation_decision(
    items: list[ExecutionStepItem],
) -> ExecutionStepItem | None:
    if not items:
        return None
    return max(items, key=lambda item: (item.created_at, item.item_index, item.id))


def continuation_decision_count_label(items: list[ExecutionStepItem]) -> str:
    if not items:
        return "-"
    follow_up_count = sum(
        1
        for item in items
        if _summary_bool(_execution_item_summary(item), "needs_follow_up")
    )
    return f"{len(items)} decisions / {follow_up_count} follow-up"


def continuation_decision_label(item: ExecutionStepItem | None) -> str:
    if item is None:
        return "-"
    summary = _execution_item_summary(item)
    reason = _summary_text(summary, "reason") or "unknown"
    end_turn = summary.get("end_turn")
    end_turn_label = (
        f"end_turn={str(end_turn).lower()}"
        if isinstance(end_turn, bool)
        else "end_turn=-"
    )
    follow_up = _summary_bool(summary, "needs_follow_up")
    parts = [reason, end_turn_label, f"follow_up={str(follow_up).lower()}"]
    provider_state = summary.get("provider_continuation_state")
    provider_state = dict(provider_state) if isinstance(provider_state, dict) else {}
    provider_mode = _optional_metadata_text(provider_state.get("mode"))
    provider_transport = _optional_metadata_text(provider_state.get("transport"))
    previous_response_id = _optional_metadata_text(
        provider_state.get("previous_response_id"),
    )
    fallback_reason = _optional_metadata_text(provider_state.get("fallback_reason"))
    if provider_mode is not None:
        parts.append(f"provider={provider_mode}")
    if provider_transport is not None:
        parts.append(f"transport={provider_transport}")
    if previous_response_id is not None:
        parts.append(f"previous_response_id={previous_response_id}")
    if fallback_reason is not None:
        parts.append(f"fallback={fallback_reason}")
    return "; ".join(parts)


def llm_tool_only_streaks(
    items_by_step_id: dict[str, tuple[ExecutionStepItem, ...]],
    *,
    steps: list[ExecutionStep],
) -> dict[str, object]:
    total = 0
    current = 0
    maximum = 0
    for step in sorted(steps, key=lambda item: item.step_index):
        if step.kind.value != "llm":
            continue
        step_items = items_by_step_id.get(step.id, ())
        if _llm_step_is_tool_only(step_items):
            total += 1
            current += 1
            maximum = max(maximum, current)
            continue
        current = 0
    return {
        "total": total,
        "current": current,
        "max": maximum,
        "suspected": maximum >= 3,
    }


def llm_tool_only_streak_label(streaks: dict[str, object]) -> str:
    maximum = _int_value(streaks.get("max"))
    current = _int_value(streaks.get("current"))
    total = _int_value(streaks.get("total"))
    if maximum <= 0:
        return "-"
    suffix = " suspected" if streaks.get("suspected") is True else ""
    return f"max {maximum} / current {current} / total {total}{suffix}"


def _llm_step_is_tool_only(items: tuple[ExecutionStepItem, ...]) -> bool:
    has_tool_call = False
    has_text = False
    has_progress = False
    for item in items:
        if item.kind.value == "tool_call":
            has_tool_call = True
        if item.kind.value == "session_message":
            summary = _execution_item_summary(item)
            if _summary_text(summary, "message_kind") == "assistant_progress":
                has_progress = True
        summary = _execution_item_summary(item)
        if _summary_bool(summary, "text_present"):
            has_text = True
        if _summary_text(summary, "assistant_progress_text") is not None:
            has_text = True
            has_progress = True
        if _summary_text_list(summary, "assistant_progress_item_ids"):
            has_progress = True
        if _summary_text_list(summary, "session_item_ids") and _summary_text(
            summary,
            "message_kind",
        ) == "assistant_progress":
            has_progress = True
        if _summary_text_list(summary, "tool_call_names"):
            has_tool_call = True
    return has_tool_call and not has_text and not has_progress


def _execution_item_summary(item: ExecutionStepItem) -> dict[str, object]:
    summary = item.summary_payload
    return dict(summary) if isinstance(summary, dict) else {}


def _summary_text(summary: dict[str, object], key: str) -> str | None:
    value = summary.get(key)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _summary_bool(summary: dict[str, object], key: str) -> bool:
    value = summary.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _summary_text_list(summary: dict[str, object], key: str) -> tuple[str, ...]:
    raw = summary.get(key)
    if not isinstance(raw, (list, tuple)):
        return ()
    values: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if text:
            values.append(text)
    return tuple(values)


def _optional_metadata_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return 0
