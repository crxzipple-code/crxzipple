from __future__ import annotations

from dataclasses import dataclass, field

from crxzipple.modules.workbench.application.entity_detail_llm import (
    llm_invocation_detail_payload,
)
from crxzipple.modules.workbench.application.entity_detail_tool import (
    tool_run_detail_payload,
)
from crxzipple.modules.workbench.application.entity_detail_values import enum_or_text


@dataclass(frozen=True, slots=True)
class WorkbenchLinkedEntityDetail:
    type: str
    id: str
    owner: str
    label: str
    summary: str
    payload: dict[str, object] = field(default_factory=dict)


def llm_response_item_detail(item: object) -> WorkbenchLinkedEntityDetail:
    payload = item.to_payload()
    kind = enum_or_text(getattr(item, "kind", None)) or "llm_response_item"
    sequence_no = getattr(item, "sequence_no", None)
    label = f"{kind} #{sequence_no}" if sequence_no is not None else kind
    return WorkbenchLinkedEntityDetail(
        type="llm_response_item",
        id=str(getattr(item, "id")),
        owner="llm",
        label=label,
        summary=_entity_detail_summary(payload),
        payload=payload,
    )


def llm_invocation_detail(
    invocation: object,
    *,
    fallback_id: str,
) -> WorkbenchLinkedEntityDetail:
    payload = llm_invocation_detail_payload(invocation)
    return WorkbenchLinkedEntityDetail(
        type="llm_invocation",
        id=str(getattr(invocation, "id", fallback_id)),
        owner="llm",
        label=str(getattr(invocation, "llm_id", "LLM invocation")),
        summary=_entity_detail_summary(payload),
        payload=payload,
    )


def session_item_detail(item: object) -> WorkbenchLinkedEntityDetail:
    payload = item.to_payload()
    kind = enum_or_text(getattr(item, "kind", None)) or "session_item"
    sequence_no = getattr(item, "sequence_no", None)
    label = f"{kind} #{sequence_no}" if sequence_no is not None else kind
    return WorkbenchLinkedEntityDetail(
        type="session_item",
        id=str(getattr(item, "id")),
        owner="session",
        label=label,
        summary=_entity_detail_summary(payload),
        payload=payload,
    )


def tool_run_detail(tool_run: object) -> WorkbenchLinkedEntityDetail:
    payload = tool_run_detail_payload(tool_run)
    return WorkbenchLinkedEntityDetail(
        type="tool_run",
        id=str(getattr(tool_run, "id")),
        owner="tool",
        label=str(getattr(tool_run, "tool_id", "tool_run")),
        summary=_entity_detail_summary(payload),
        payload=payload,
    )


def _entity_detail_summary(payload: dict[str, object]) -> str:
    runtime_observations = payload.get("runtime_observations")
    if isinstance(runtime_observations, dict):
        summary = runtime_observations.get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()[:240]
    result_summary = payload.get("result_summary")
    if isinstance(result_summary, str) and result_summary.strip():
        return result_summary.strip()[:240]
    content = payload.get("content_payload")
    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()[:240]
        blocks = content.get("blocks")
        if isinstance(blocks, list):
            texts = [
                block.get("text", "").strip()
                for block in blocks
                if isinstance(block, dict) and isinstance(block.get("text"), str)
            ]
            joined = " ".join(text for text in texts if text)
            if joined:
                return joined[:240]
        tool_name = content.get("tool_name") or content.get("name")
        if isinstance(tool_name, str) and tool_name.strip():
            return tool_name.strip()
    for key in ("tool_name", "provider_item_type", "kind", "role"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return str(payload.get("kind") or payload.get("role") or "entity")
