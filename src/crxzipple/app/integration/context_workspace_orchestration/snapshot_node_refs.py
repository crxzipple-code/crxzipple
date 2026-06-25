"""Snapshot metadata helpers for session-related context node references."""

from __future__ import annotations

from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
    RuntimeLlmRequestDraft,
)
from crxzipple.modules.orchestration.domain import OrchestrationRun


def session_item_node_refs(
    included_node_ids: tuple[str, ...],
) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    prefix = "session.item."
    for node_id in included_node_ids:
        if not node_id.startswith(prefix):
            continue
        tail = node_id[len(prefix):]
        session_id, separator, sequence_text = tail.rpartition(".")
        if not separator or not session_id or not sequence_text.isdigit():
            refs.append({"node_id": node_id})
            continue
        refs.append(
            {
                "node_id": node_id,
                "session_id": session_id,
                "sequence_no": int(sequence_text),
            },
        )
    return refs


def tool_interaction_node_refs(
    included_node_ids: tuple[str, ...],
) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    prefix = "session.tool_interaction."
    for node_id in included_node_ids:
        if not node_id.startswith(prefix):
            continue
        refs.append({"node_id": node_id})
    return refs


def evidence_node_refs(
    included_node_ids: tuple[str, ...],
) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    prefix = "session.evidence."
    for node_id in included_node_ids:
        if not node_id.startswith(prefix) or node_id == "session.evidence.current":
            continue
        refs.append({"node_id": node_id})
    return refs


def current_inbound_node_id(
    *,
    run: OrchestrationRun,
    draft: RuntimeLlmRequestDraft,
    included_node_ids: tuple[str, ...],
) -> str | None:
    included = set(included_node_ids)
    for message in draft.messages:
        metadata = message.metadata
        if metadata.get("source_kind") != "orchestration_run":
            continue
        if metadata.get("source_id") != run.id:
            continue
        session_id = metadata.get("session_id")
        sequence_no = metadata.get("sequence_no")
        if not isinstance(session_id, str) or not session_id.strip():
            continue
        if isinstance(sequence_no, int):
            sequence_text = str(sequence_no)
        elif isinstance(sequence_no, str) and sequence_no.strip().isdigit():
            sequence_text = sequence_no.strip()
        else:
            continue
        node_id = f"session.item.{session_id.strip()}.{sequence_text}"
        if node_id in included:
            return node_id
    return None


def current_inbound_session_item_id(
    *,
    run: OrchestrationRun,
    draft: RuntimeLlmRequestDraft,
) -> str | None:
    for message in draft.messages:
        metadata = message.metadata
        if metadata.get("source_kind") != "orchestration_run":
            continue
        if metadata.get("source_id") != run.id:
            continue
        session_item_id = metadata.get("session_item_id")
        if isinstance(session_item_id, str) and session_item_id.strip():
            return session_item_id.strip()
    return None
