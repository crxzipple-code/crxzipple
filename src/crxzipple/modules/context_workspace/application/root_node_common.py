from __future__ import annotations

from crxzipple.modules.context_workspace.application.runtime_contract import (
    RuntimeContract,
)
from crxzipple.modules.context_workspace.domain import ContextEstimate


def runtime_contract_estimate(contract: RuntimeContract) -> ContextEstimate:
    return text_estimate(contract.content)


def context_block_payload(
    metadata: dict[str, object] | None,
    *,
    key: str,
    default_summary: str,
) -> dict[str, object]:
    raw = (metadata or {}).get(key)
    if not isinstance(raw, dict):
        return {"summary": default_summary, "content": "", "metadata": {}}
    content = optional_text(raw.get("content")) or ""
    summary = optional_text(raw.get("summary")) or default_summary
    raw_metadata = raw.get("metadata")
    node_metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
    if bool(raw.get("truncated")):
        node_metadata["truncated"] = True
    return {
        "summary": truncate(summary, 1900),
        "content": content,
        "metadata": node_metadata,
    }


def run_flow_payload(metadata: dict[str, object] | None) -> dict[str, object]:
    raw = (metadata or {}).get("run_flow_node")
    if isinstance(raw, dict):
        mode = optional_text(raw.get("mode")) or "normal_turn"
        title = optional_text(raw.get("title")) or title_for_mode(mode)
        summary = truncate(
            optional_text(raw.get("summary")) or summary_for_mode(mode),
            1900,
        )
        raw_metadata = raw.get("metadata")
        node_metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
        node_metadata.setdefault("mode", mode)
        return {
            "mode": mode,
            "title": title,
            "summary": summary,
            "metadata": node_metadata,
        }
    mode = optional_text((metadata or {}).get("runtime_request_mode")) or "normal_turn"
    return {
        "mode": mode,
        "title": title_for_mode(mode),
        "summary": summary_for_mode(mode),
        "metadata": {"mode": mode},
    }


def title_for_mode(mode: str) -> str:
    return {
        "session_start": "Flow: Session Start",
        "approval_resume": "Flow: Approval Resume",
        "approval_denied": "Flow: Approval Denied",
        "recovery_resume": "Flow: Recovery Resume",
        "heartbeat": "Flow: Heartbeat",
        "memory_flush": "Flow: Memory Flush",
        "compaction": "Flow: Compaction",
    }.get(mode, "Flow: Normal Turn")


def summary_for_mode(mode: str) -> str:
    if mode == "session_start":
        return "Start a fresh active session using only visible transcript, context tree, and memory nodes."
    if mode == "approval_resume":
        return "Resume the interrupted task after an approval update without restarting from scratch."
    if mode == "approval_denied":
        return "Continue with available tools and access after the requested approval was denied."
    if mode == "recovery_resume":
        return "Resume paused work after background results became available."
    if mode == "heartbeat":
        return "Handle a lightweight heartbeat and avoid broad exploratory work unless there is clear unfinished work."
    if mode == "memory_flush":
        return "Capture durable memory only; do not answer the user conversation in this run."
    if mode == "compaction":
        return "Compact the session into a concise factual continuation summary."
    return "Handle the latest user request using visible context tree nodes, transcript, and callable tool schemas."


def text_estimate(text: str) -> ContextEstimate:
    normalized = text or ""
    return ContextEstimate(
        text_chars=len(normalized),
        text_tokens=max((len(normalized) + 3) // 4, 1) if normalized else 0,
    )


def optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def truncate(value: str, limit: int) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)].rstrip() + "..."
