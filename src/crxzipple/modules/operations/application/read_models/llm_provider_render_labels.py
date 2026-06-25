from __future__ import annotations

import json
from typing import Any

from crxzipple.modules.llm.domain import LlmInvocation
from crxzipple.modules.operations.application.read_models.llm_invocation_labels import (
    provider_render_report,
    provider_request_preview,
)


def provider_request_renderer_label(invocation: LlmInvocation) -> str:
    preview = provider_request_preview(invocation)
    value = _text(preview.get("renderer_id"))
    if value:
        return value
    render_report = preview.get("render_report")
    if isinstance(render_report, dict):
        value = _text(render_report.get("renderer_id"))
        if value:
            return value
    return "-"


def provider_request_render_strategy_label(invocation: LlmInvocation) -> str:
    preview = provider_request_preview(invocation)
    value = _text(preview.get("render_strategy"))
    if value:
        return value
    render_report = preview.get("render_report")
    if isinstance(render_report, dict):
        value = _text(render_report.get("render_strategy"))
        if value:
            return value
    return "-"


def provider_request_render_report_label(invocation: LlmInvocation) -> str:
    preview = provider_request_preview(invocation)
    render_report = preview.get("render_report")
    if not isinstance(render_report, dict) or not render_report:
        return "-"
    parts: list[str] = []
    renderer_id = _text(render_report.get("renderer_id"))
    transport = _text(render_report.get("transport"))
    strategy = _text(render_report.get("render_strategy"))
    if renderer_id:
        parts.append(f"renderer={renderer_id}")
    if transport:
        parts.append(f"transport={transport}")
    if strategy:
        parts.append(f"strategy={strategy}")
    loss_report = render_report.get("loss_report")
    if isinstance(loss_report, dict) and loss_report:
        parts.append(f"loss={_truncate(_json_or_text(loss_report), 160)}")
    elif isinstance(loss_report, dict):
        parts.append("loss=none")
    return "; ".join(parts) if parts else _truncate(_json_or_text(render_report), 240)


def provider_tool_mapping_label(invocation: LlmInvocation) -> str:
    render_report = provider_render_report(invocation)
    tool_surface = render_report.get("tool_surface")
    if not isinstance(tool_surface, dict):
        return "-"
    mapping = tool_surface.get("provider_tool_mapping")
    if not isinstance(mapping, list) or not mapping:
        return "-"
    traced = 0
    untraced = 0
    samples: list[str] = []
    for raw_row in mapping:
        if not isinstance(raw_row, dict):
            continue
        status = _text(raw_row.get("trace_status"))
        if status == "runtime_tool_surface":
            traced += 1
        else:
            untraced += 1
        if len(samples) >= 3:
            continue
        provider_name = _text(raw_row.get("provider_name")) or "?"
        node_id = _text(raw_row.get("node_id"))
        source_id = _text(raw_row.get("source_id"))
        target = node_id or source_id or _text(raw_row.get("tool_id")) or "untraced"
        samples.append(f"{provider_name}->{target}")
    if not traced and not untraced:
        return "-"
    parts = [f"traced={traced}", f"untraced={untraced}"]
    if samples:
        parts.append("sample=" + ", ".join(samples))
    return "; ".join(parts)


def _json_or_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def _truncate(value: Any, limit: int = 160) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)] + "..."


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
