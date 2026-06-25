from __future__ import annotations

from typing import Any

from crxzipple.modules.channels.application.runtime_helpers import (
    session_item_fact_as_message_payload,
)
from crxzipple.shared.content_blocks import (
    content_blocks_from_payload,
    describe_content_for_text_fallback,
)


def lark_observe_session_message_fact(payload: dict[str, Any]) -> dict[str, Any]:
    payload = session_item_fact_as_message_payload(payload)
    message = dict(payload.get("message") or {})
    content_payload = dict(message.get("content_payload") or {})
    blocks = content_blocks_from_payload(content_payload)
    artifact_refs = extract_artifact_refs_from_blocks(blocks)
    block_types = [
        str(block.get("type") or "").strip()
        for block in blocks
        if str(block.get("type") or "").strip()
    ]
    text_fragments = [
        str(block.get("text") or "")
        for block in blocks
        if str(block.get("type") or "").strip() == "text"
        and str(block.get("text") or "").strip()
    ]
    summary_text = "\n".join(text_fragments) if text_fragments else None
    if summary_text is None and content_payload:
        summary_text = describe_content_for_text_fallback(content_payload)
    observation: dict[str, Any] = {
        "last_message_id": str(payload.get("message_id") or "").strip() or None,
        "last_message_role": str(payload.get("role") or "").strip() or None,
        "last_message_kind": str(payload.get("kind") or "").strip() or None,
        "last_message_source_kind": (
            str(payload.get("source_kind") or "").strip() or None
        ),
        "last_message_source_id": (
            str(payload.get("source_id") or "").strip() or None
        ),
        "last_message_created_at": message.get("created_at"),
        "last_message_summary": summary_text,
        "last_message_block_types": block_types,
        "last_message_artifact_refs": artifact_refs,
        "last_message_has_image_artifacts": any(
            block_type in {"image", "image_ref"}
            for block_type in block_types
        ),
        "last_message_has_file_artifacts": any(
            block_type in {"file", "file_ref"}
            for block_type in block_types
        ),
    }
    if observation["last_message_kind"] == "tool_result":
        observation["last_tool_result"] = {
            "tool_name": str(content_payload.get("tool_name") or "").strip() or None,
            "tool_call_id": (
                str(content_payload.get("tool_call_id") or "").strip() or None
            ),
            "tool_run_id": (
                str(content_payload.get("tool_run_id") or "").strip() or None
            ),
            "status": str(content_payload.get("status") or "").strip() or None,
            "summary": summary_text,
            "artifact_refs": artifact_refs,
        }
    if observation["last_message_role"] == "assistant":
        observation["last_assistant_message_summary"] = summary_text
        observation["last_assistant_message_artifact_refs"] = artifact_refs
    return observation


def extract_artifact_refs_from_blocks(
    blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    artifact_refs: list[dict[str, Any]] = []
    for block in blocks:
        artifact_id = str(block.get("artifact_id") or "").strip()
        if not artifact_id:
            continue
        artifact_refs.append(
            {
                "type": str(block.get("type") or "").strip() or None,
                "artifact_id": artifact_id,
                "mime_type": str(block.get("mime_type") or "").strip() or None,
                "name": str(block.get("name") or "").strip() or None,
                "preview_url": str(block.get("preview_url") or "").strip() or None,
                "original_url": str(block.get("original_url") or "").strip() or None,
                "download_url": str(block.get("download_url") or "").strip() or None,
            }
        )
    return artifact_refs
