from __future__ import annotations

from crxzipple.modules.workbench.application import view_models as models
from typing import Any

from crxzipple.modules.workbench.application.execution_projection import (
    assistant_progress_session_item_ids_from_execution_items,
    enum_value,
    execution_item_summary,
    llm_invocation_id_from_execution_items,
    safe_llm_invocation,
    summary_dict_from_items,
    summary_text,
    summary_text_from_items,
    tool_call_session_item_ids_from_execution_items,
)
from crxzipple.modules.workbench.application.projection_helpers import optional_text


def llm_step_diagnostics(
    llm_invocation: Any | None,
    items: tuple[Any, ...],
) -> dict[str, object]:
    result = getattr(llm_invocation, "result", None)
    text = getattr(result, "text", None)
    text_chars = len(text.strip()) if isinstance(text, str) and text.strip() else 0
    response_item_stats = _llm_response_item_diagnostic_counts(llm_invocation)
    raw_tool_calls = getattr(result, "tool_calls", None)
    tool_calls_count = len(raw_tool_calls) if isinstance(raw_tool_calls, (tuple, list)) else 0
    if tool_calls_count == 0:
        tool_calls_count = len(_tool_call_names_from_execution_items(items))
    if tool_calls_count == 0:
        tool_calls_count = response_item_stats["tool_call_count"]
    tool_call_item_count = len(
        tool_call_session_item_ids_from_execution_items(items),
    )
    progress_count = len(
        assistant_progress_session_item_ids_from_execution_items(items),
    )
    if progress_count == 0 and summary_text_from_items(
        items,
        "assistant_progress_text",
    ):
        progress_count = 1
    if progress_count == 0:
        progress_count = response_item_stats["progress_item_count"]
    if text_chars == 0:
        progress_text = summary_text_from_items(
            items,
            "assistant_progress_text",
        )
        text_chars = len(progress_text) if progress_text is not None else 0
    if text_chars == 0:
        text_chars = response_item_stats["text_chars"]
    diagnostics: dict[str, object] = {
        "text_present": text_chars > 0,
        "text_chars": text_chars,
        "tool_calls_count": tool_calls_count,
        "tool_call_session_item_count": tool_call_item_count,
        "progress_recorded": progress_count > 0,
        "assistant_progress_item_count": progress_count,
        "llm_response_item_count": response_item_stats["response_item_count"],
        "llm_reasoning_text_item_count": response_item_stats["reasoning_text_count"],
    }
    loop_diagnostic = summary_dict_from_items(items, "llm_loop_diagnostic")
    code = summary_text(loop_diagnostic, "code") if loop_diagnostic else None
    reason = summary_text(loop_diagnostic, "reason") if loop_diagnostic else None
    if code is not None:
        diagnostics["loop_diagnostic_code"] = code
    if reason is not None:
        diagnostics["loop_diagnostic_reason"] = reason
    return diagnostics


def _llm_response_item_diagnostic_counts(llm_invocation: Any | None) -> dict[str, int]:
    response_items = tuple(getattr(llm_invocation, "response_items", ()) or ())
    response_item_count = 0
    tool_call_count = 0
    progress_item_count = 0
    reasoning_text_count = 0
    text_chars = 0
    for response_item in response_items:
        response_item_count += 1
        kind = enum_value(getattr(response_item, "kind", None))
        if kind == "tool_call":
            tool_call_count += 1
            continue
        if kind not in {"assistant_message", "reasoning"}:
            continue
        payload = dict(getattr(response_item, "content_payload", {}) or {})
        text = _response_item_visible_text(payload)
        if text is None:
            continue
        text_chars += len(text)
        progress_item_count += 1
        if kind == "reasoning":
            reasoning_text_count += 1
    return {
        "response_item_count": response_item_count,
        "tool_call_count": tool_call_count,
        "progress_item_count": progress_item_count,
        "reasoning_text_count": reasoning_text_count,
        "text_chars": text_chars,
    }


def _response_item_visible_text(payload: dict[str, object]) -> str | None:
    text = optional_text(payload.get("text")) or optional_text(
        payload.get("summary"),
    )
    if text is not None:
        return text
    summary = payload.get("summary")
    if not isinstance(summary, (list, tuple)):
        return None
    fragments: list[str] = []
    for item in summary:
        if isinstance(item, dict):
            item_text = optional_text(item.get("text"))
        else:
            item_text = optional_text(item)
        if item_text is not None:
            fragments.append(item_text)
    return "\n".join(fragments) if fragments else None


def llm_bundle_is_tool_only(
    bundle: Any,
    *,
    llm_query: Any | None,
) -> bool:
    invocation_id = llm_invocation_id_from_execution_items(bundle.items)
    llm_invocation = safe_llm_invocation(llm_query, invocation_id)
    diagnostics = llm_step_diagnostics(llm_invocation, bundle.items)
    return (
        diagnostics.get("tool_calls_count", 0) > 0
        and diagnostics.get("text_present") is False
        and diagnostics.get("progress_recorded") is False
    )


def llm_diagnostics_sentence(diagnostics: dict[str, object]) -> str:
    text_chars = diagnostics.get("text_chars")
    tool_calls_count = diagnostics.get("tool_calls_count")
    tool_call_item_count = diagnostics.get("tool_call_session_item_count")
    progress_count = diagnostics.get("assistant_progress_item_count")
    parts: list[str] = []
    if isinstance(text_chars, int) and text_chars > 0:
        parts.append(f"text: {text_chars} chars")
    elif isinstance(tool_calls_count, int) and tool_calls_count > 0:
        parts.append("text: none")
    if isinstance(tool_calls_count, int) and tool_calls_count > 0:
        parts.append(f"tool calls: {tool_calls_count}")
    if isinstance(tool_call_item_count, int) and tool_call_item_count > 0:
        parts.append(f"tool call items: {tool_call_item_count}")
    if isinstance(progress_count, int) and progress_count > 0:
        parts.append(f"progress recorded: {progress_count}")
    loop_code = diagnostics.get("loop_diagnostic_code")
    if isinstance(loop_code, str) and loop_code:
        parts.append(f"loop diagnostic: {loop_code}")
    if not parts:
        return ""
    return "Diagnostics: " + "; ".join(parts) + "."


def llm_diagnostic_badges(diagnostics: dict[str, object]) -> tuple[Any, ...]:
    tool_calls_count = diagnostics.get("tool_calls_count")
    tool_call_item_count = diagnostics.get("tool_call_session_item_count")
    text_present = diagnostics.get("text_present") is True
    progress_recorded = diagnostics.get("progress_recorded") is True
    badges: list[Any] = []
    if isinstance(tool_calls_count, int) and tool_calls_count > 0:
        badges.append(
            models.StatusBadgeModel(
                label="Text + tools" if text_present else "Tool only",
                tone="success" if text_present else "warning",
            ),
        )
    elif text_present:
        badges.append(models.StatusBadgeModel(label="Text", tone="success"))
    if progress_recorded:
        badges.append(models.StatusBadgeModel(label="Progress recorded", tone="info"))
    if isinstance(tool_call_item_count, int) and tool_call_item_count > 0:
        badges.append(
            models.StatusBadgeModel(
                label=f"Tool items: {tool_call_item_count}",
                tone="info",
            ),
        )
    loop_code = diagnostics.get("loop_diagnostic_code")
    if isinstance(loop_code, str) and loop_code:
        badges.append(models.StatusBadgeModel(label="Loop diagnostic", tone="danger"))
    return tuple(badges)


def tool_only_streak_badges(tool_only_streak: int) -> tuple[Any, ...]:
    if tool_only_streak < 3:
        return ()
    return (
        models.StatusBadgeModel(
            label=f"Tool-only streak: {tool_only_streak}",
            tone="warning",
        ),
    )


def _tool_call_names_from_execution_items(items: tuple[Any, ...]) -> tuple[str, ...]:

    names: list[str] = []
    for item in items:
        summary = execution_item_summary(item)
        raw_names = summary.get("tool_call_names")
        if isinstance(raw_names, (list, tuple)):
            for raw_name in raw_names:
                if not isinstance(raw_name, str):
                    continue
                name = raw_name.strip()
                if name and name not in names:
                    names.append(name)
    return tuple(names)
