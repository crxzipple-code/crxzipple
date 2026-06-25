from __future__ import annotations

from typing import Any

from crxzipple.modules.workbench.application.projection_helpers import optional_text


def step_should_be_visible_in_timeline(step: Any) -> bool:
    if step.type in {"agent_progress", "agent_thinking"}:
        return _step_has_visible_narrative(step)
    if step.type == "llm":
        return step.status not in {"success", "completed"}
    if step.type == "continuation_decision":
        return _continuation_decision_is_actionable(step)
    return True


def deduplicate_timeline_items(
    items: tuple[Any, ...],
) -> tuple[Any, ...]:
    response_final_turns = {
        item.turn_id
        for item in items
        if item.kind == "final_answer"
        and item.source_refs.get("llm_response_item_id")
    }
    response_commentary_texts = {
        (item.turn_id, timeline_item_text(item))
        for item in items
        if item.kind == "assistant_commentary"
        and item.source_refs.get("llm_response_item_id")
        and timeline_item_text(item) is not None
    }
    if not response_final_turns and not response_commentary_texts:
        return items
    return tuple(
        item
        for item in items
        if not (
            item.kind == "final_answer"
            and item.turn_id in response_final_turns
            and not item.source_refs.get("llm_response_item_id")
        )
        and not (
            item.kind == "assistant_commentary"
            and not item.source_refs.get("llm_response_item_id")
            and (item.turn_id, timeline_item_text(item)) in response_commentary_texts
        )
    )


def timeline_item_text(item: Any) -> str | None:
    return optional_text(item.content.get("text")) or optional_text(
        item.content.get("markdown"),
    )


def response_item_is_internal_control_tool(response_item: Any) -> bool:
    if enum_value(getattr(response_item, "kind", None)) != "tool_call":
        return False
    tool_name = optional_text(getattr(response_item, "tool_name", None))
    return bool(tool_name and tool_name.startswith("context_tree."))


def timeline_user_payload_for_response_item(response_item: Any) -> dict[str, Any]:
    payload = dict(getattr(response_item, "content_payload", {}) or {})
    kind = enum_value(getattr(response_item, "kind", None))
    if kind in {"assistant_message", "reasoning", "compaction"}:
        return _pick_payload_keys(payload, ("text", "summary", "markdown"))
    if kind == "tool_call":
        return _pick_payload_keys(payload, ("call_id", "tool_name"))
    if kind == "provider_external_item":
        return _pick_payload_keys(
            payload,
            ("status", "type", "title", "name", "query", "url"),
        )
    if kind == "structured_output":
        return _pick_payload_keys(payload, ("text", "summary", "title", "status"))
    return _pick_payload_keys(payload, ("text", "summary", "title", "status"))


def response_item_has_timeline_content(
    response_item: Any,
    content: dict[str, Any],
) -> bool:
    kind = enum_value(getattr(response_item, "kind", None))
    if kind == "reasoning":
        if bool(content.get("reasoning_hidden")):
            return True
        return timeline_content_has_visible_value(content)
    if kind != "assistant_message":
        return True
    text = optional_text(content.get("text"))
    markdown = optional_text(content.get("markdown"))
    payload = content.get("payload")
    return bool(text or markdown or payload_has_visible_value(payload))


def timeline_content_has_visible_value(content: dict[str, Any]) -> bool:
    if optional_text(content.get("text")) is not None:
        return True
    if optional_text(content.get("markdown")) is not None:
        return True
    return payload_has_visible_value(content.get("payload"))


def payload_has_visible_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, bool | int | float):
        return True
    if isinstance(value, dict):
        return any(payload_has_visible_value(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(payload_has_visible_value(item) for item in value)
    return True


def suppress_loop_control_timeline_items(
    items: tuple[Any, ...],
) -> tuple[Any, ...]:
    return tuple(
        item
        for item in items
        if not timeline_item_is_debug_only_continuation(item)
    )


def timeline_item_is_debug_only_continuation(item: Any) -> bool:
    if item.kind != "continuation":
        return False
    text = str(item.content.get("text") or item.content.get("summary") or "").strip()
    if not text:
        text = item.title.strip()
    normalized = text.lower()
    return normalized.startswith("none;") or normalized.startswith("tool_call;")


def enum_value(value: Any) -> str | None:
    if value is None:
        return None
    enum_value_value = getattr(value, "value", None)
    if isinstance(enum_value_value, str):
        return enum_value_value
    text = str(value).strip()
    return text or None


def _pick_payload_keys(
    payload: dict[str, Any],
    keys: tuple[str, ...],
) -> dict[str, Any]:
    return {
        key: payload[key]
        for key in keys
        if key in payload and payload[key] not in (None, {}, [], ())
    }


def _step_has_visible_narrative(step: Any) -> bool:
    if optional_text(step.summary) is not None:
        return True
    if optional_text(step.markdown) is not None:
        return True
    return False


def _continuation_decision_is_actionable(step: Any) -> bool:
    if step.status not in {"success", "completed"}:
        return True
    summary = (step.summary or "").strip().lower()
    if not summary:
        return False
    parts = [part.strip() for part in summary.split(";")]
    reason = parts[0] if parts else ""
    has_follow_up = "follow_up=true" in summary
    continues_turn = "end_turn=false" in summary
    if has_follow_up or continues_turn:
        return True
    return reason not in {"none", "unknown", ""}
