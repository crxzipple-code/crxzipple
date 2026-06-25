from __future__ import annotations

from crxzipple.modules.workbench.application import view_models as models
from typing import Any

from crxzipple.modules.workbench.application.projection_helpers import optional_text
from crxzipple.modules.workbench.application.timeline_refs import (
    timeline_source_refs,
)
from crxzipple.modules.workbench.application.timeline_visibility import (
    enum_value,
    response_item_has_timeline_content,
    response_item_is_internal_control_tool,
    timeline_user_payload_for_response_item,
)
from crxzipple.shared.time import format_optional_datetime_utc


def timeline_items_from_llm_response_items(
    step: Any,
    *,
    response_items: tuple[Any, ...],
    base_index: int,
) -> tuple[Any, ...]:
    items: list[Any] = []
    for item_index, response_item in enumerate(response_items):
        if response_item_is_internal_control_tool(response_item):
            continue
        content = timeline_content_from_response_item(response_item)
        if not response_item_has_timeline_content(response_item, content):
            continue
        source_refs = timeline_source_refs(step)
        response_item_id = optional_text(getattr(response_item, "id", None))
        provider_item_id = optional_text(
            getattr(response_item, "provider_item_id", None),
        )
        call_id = optional_text(getattr(response_item, "call_id", None))
        if response_item_id is not None:
            source_refs["llm_response_item_id"] = response_item_id
        if provider_item_id is not None:
            source_refs["provider_item_id"] = provider_item_id
        if call_id is not None:
            source_refs["call_id"] = call_id
        items.append(
            models.WorkbenchTimelineItem(
                id=f"timeline:{step.step_id}:response:{base_index}:{item_index}",
                turn_id=step.turn_id,
                run_id=step.run_id,
                kind=timeline_kind_for_response_item(response_item),
                status=(
                    "success"
                    if getattr(response_item, "completed_at", None)
                    else step.status
                ),
                title=timeline_title_for_response_item(response_item),
                content=content,
                phase=enum_value(getattr(response_item, "phase", None)),
                source_refs=source_refs,
                started_at=format_optional_datetime_utc(
                    getattr(response_item, "created_at", None),
                ),
                completed_at=format_optional_datetime_utc(
                    getattr(response_item, "completed_at", None),
                ),
                trace=step.trace,
            ),
        )
    return tuple(items)


def timeline_content_from_response_item(response_item: Any) -> dict[str, Any]:
    kind = enum_value(getattr(response_item, "kind", None))
    if kind == "reasoning" and not bool(
        getattr(response_item, "user_timeline_candidate", False),
    ):
        return {
            "reasoning_present": True,
            "reasoning_item_count": 1,
            "reasoning_hidden": True,
            "hidden_reason": "policy",
        }
    payload = timeline_user_payload_for_response_item(response_item)
    content: dict[str, Any] = {}
    text = optional_text(payload.get("text")) or optional_text(
        payload.get("summary"),
    )
    if text is not None:
        content["text"] = text
    markdown = optional_text(payload.get("markdown"))
    if markdown is not None:
        content["markdown"] = markdown
    if payload:
        content["payload"] = payload
    tool_name = optional_text(getattr(response_item, "tool_name", None))
    call_id = optional_text(getattr(response_item, "call_id", None))
    if tool_name is not None:
        content["tool_name"] = tool_name
    if call_id is not None:
        content["call_id"] = call_id
    return content


def timeline_kind_for_response_item(response_item: Any) -> str:
    kind = enum_value(getattr(response_item, "kind", None))
    phase = enum_value(getattr(response_item, "phase", None))
    if kind == "assistant_message":
        return "final_answer" if phase == "final_answer" else "assistant_commentary"
    if kind == "reasoning":
        return "reasoning_summary"
    if kind == "provider_external_item":
        return "provider_external_activity"
    if kind == "structured_output":
        return "structured_output"
    if kind == "compaction":
        return "context_compaction"
    return kind or "unknown"


def timeline_title_for_response_item(response_item: Any) -> str:

    kind = timeline_kind_for_response_item(response_item)
    if kind == "assistant_commentary":
        return "Agent Progress"
    if kind == "final_answer":
        return "Final Response"
    if kind == "reasoning_summary":
        return "Reasoning Summary"
    if kind == "tool_call":
        tool_name = optional_text(getattr(response_item, "tool_name", None))
        return f"Tool Call: {tool_name}" if tool_name else "Tool Call"
    if kind == "tool_result":
        return "Tool Result"
    if kind == "provider_external_activity":
        provider_type = optional_text(
            getattr(response_item, "provider_item_type", None),
        )
        return (
            f"Provider Activity: {provider_type}"
            if provider_type
            else "Provider Activity"
        )
    return kind.replace("_", " ").title()
