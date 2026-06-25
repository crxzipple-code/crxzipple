from __future__ import annotations

from collections.abc import Callable
from typing import Any

from crxzipple.modules.operations.application.read_models.diagnostics_common import (
    enum_value,
    joined_text_values,
    optional_int,
    optional_text,
    summary_list,
    summary_payload,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    ExecutionStepItemKind,
)


def response_item_metrics(
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
            enum_value(getattr(item, "kind", ""))
            != ExecutionStepItemKind.LLM_INVOCATION.value
        ):
            continue
        item_id = str(getattr(item, "id", ""))
        payload = summary_payload(item)
        response_item_ids = [
            text
            for raw_id in summary_list(payload, "llm_response_item_ids")
            if (text := optional_text(raw_id)) is not None
        ]
        resolved_items = [
            resolved
            for resolved in (
                _resolve_response_item(
                    response_item_id,
                    resolver=response_item_resolver,
                    cache=response_item_cache,
                )
                for response_item_id in response_item_ids
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
            has_tool_call = bool(summary_list(payload, "tool_call_names"))
            has_progress = bool(
                summary_list(payload, "assistant_progress_item_ids"),
            ) or bool(optional_text(payload.get("assistant_progress_text")))
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


def request_input_metrics(items: tuple[Any, ...]) -> dict[str, object]:
    input_mode_counts: dict[str, int] = {}
    missing_count = 0
    input_item_count = 0
    runtime_transcript_item_count = 0
    for item in items:
        if (
            enum_value(getattr(item, "kind", ""))
            != ExecutionStepItemKind.LLM_INVOCATION.value
        ):
            continue
        payload = summary_payload(item)
        request_input = payload.get("llm_request_input")
        if not isinstance(request_input, dict):
            missing_count += 1
            continue
        input_mode = optional_text(request_input.get("input_mode")) or "unknown"
        input_mode_counts[input_mode] = input_mode_counts.get(input_mode, 0) + 1
        input_item_count += optional_int(request_input.get("input_item_count"))
        if input_mode == "runtime_transcript":
            runtime_transcript_item_count += optional_int(
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
    return enum_value(getattr(response_item, "kind", ""))


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
        optional_text(payload.get("text"))
        or optional_text(payload.get("content"))
        or optional_text(payload.get("summary"))
        or optional_text(joined_text_values(payload.get("content_payload"))),
    )
