from __future__ import annotations

from crxzipple.modules.workbench.application.entity_detail_values import (
    bounded_text,
    enum_or_text,
)


def llm_replay_input_payload(invocation: object) -> dict[str, object]:
    items = tuple(getattr(invocation, "input_items", ()) or ())
    kind_values: list[str] = []
    source_values: list[str] = []
    tool_result_excerpt_samples: list[str] = []
    protocol_counts = {
        "reasoning": 0,
        "function_call": 0,
        "function_call_output": 0,
        "provider_external_item": 0,
    }
    for item in items:
        kind = enum_or_text(getattr(item, "kind", None))
        if kind:
            kind_values.append(kind)
            if kind in protocol_counts:
                protocol_counts[kind] += 1
        source = str(getattr(item, "source", "") or "").strip()
        if source:
            source_values.append(source)
        if kind == "function_call_output":
            excerpt = _llm_input_item_tool_result_excerpt(item)
            if excerpt is not None:
                tool_result_excerpt_samples.append(excerpt)
    unique_kinds = list(dict.fromkeys(kind_values))
    unique_sources = list(dict.fromkeys(source_values))
    return {
        "count": len(items),
        "kinds": unique_kinds[:12],
        "sources": unique_sources[:12],
        "kind_counts": {
            kind: kind_values.count(kind)
            for kind in unique_kinds[:12]
        },
        "tool_result_excerpt_count": len(tool_result_excerpt_samples),
        "tool_result_excerpt_sample": (
            tool_result_excerpt_samples[0] if tool_result_excerpt_samples else None
        ),
        "protocol_counts": protocol_counts,
        "summary": _llm_replay_input_summary(
            count=len(items),
            kinds=unique_kinds,
            protocol_counts=protocol_counts,
        ),
    }


def _llm_replay_input_summary(
    *,
    count: int,
    kinds: list[str],
    protocol_counts: dict[str, int],
) -> str:
    if count <= 0:
        return "No replay input items."
    kind_label = ", ".join(kinds[:4]) if kinds else "unknown"
    protocol_total = sum(protocol_counts.values())
    if protocol_total:
        return f"{count} items; {kind_label}; protocol={protocol_total}"
    return f"{count} items; {kind_label}"


def _llm_input_item_tool_result_excerpt(item: object) -> str | None:
    payload = getattr(item, "payload", None)
    if not isinstance(payload, dict):
        return None
    text = _llm_input_output_text(payload.get("output"))
    if not text.strip() or "tool_result:" not in text:
        return None
    return bounded_text(text.strip().replace("\n", " "), limit=240)


def _llm_input_output_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for block in value:
            if not isinstance(block, dict):
                continue
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
        return "\n".join(parts)
    if isinstance(value, dict):
        text = value.get("text")
        return text if isinstance(text, str) else ""
    return ""
