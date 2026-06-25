from __future__ import annotations

from crxzipple.modules.session.domain import SessionItem, SessionItemKind
from crxzipple.modules.llm.application.tool_result_replay_fields import (
    metadata_artifact_ids,
    optional_int,
    text_list,
)
from crxzipple.modules.tool.application.result_envelope import (
    TOOL_RESULT_ENVELOPE_METADATA_KEY,
)


def tool_result_item_stats(items: tuple[SessionItem, ...]) -> dict[str, object]:
    stats: dict[str, object] = {
        "tool_result_item_count": 0,
        "compacted_result_count": 0,
        "omitted_chars": 0,
        "omitted_count": 0,
        "artifact_ref_count": 0,
        "read_handle_count": 0,
    }
    artifact_refs: set[str] = set()
    for item in items:
        if item.kind is not SessionItemKind.TOOL_RESULT:
            continue
        stats["tool_result_item_count"] = int(stats["tool_result_item_count"]) + 1
        metadata = item.content_payload.get("metadata")
        details = item.content_payload.get("details")
        if not isinstance(metadata, dict):
            metadata = {}
        if not isinstance(details, dict):
            details = {}
        envelope = metadata.get(TOOL_RESULT_ENVELOPE_METADATA_KEY)
        artifact_ids = metadata_artifact_ids(metadata)
        for artifact_id in artifact_ids:
            artifact_refs.add(artifact_id)
        if not isinstance(envelope, dict):
            if artifact_ids or details.get("body_removed_from_details") is True:
                stats["compacted_result_count"] = (
                    int(stats["compacted_result_count"]) + 1
                )
            continue
        if (
            envelope.get("truncated") is True
            or artifact_ids
            or details.get("body_removed_from_details") is True
        ):
            stats["compacted_result_count"] = (
                int(stats["compacted_result_count"]) + 1
            )
        stats["omitted_chars"] = int(stats["omitted_chars"]) + (
            optional_int(envelope.get("omitted_chars")) or 0
        )
        stats["omitted_count"] = int(stats["omitted_count"]) + (
            optional_int(envelope.get("omitted_count")) or 0
        )
        for artifact_id in text_list(envelope.get("evidence_refs")):
            artifact_refs.add(artifact_id)
        read_handles = envelope.get("read_handles")
        if isinstance(read_handles, list):
            stats["read_handle_count"] = (
                int(stats["read_handle_count"]) + len(read_handles)
            )
    stats["artifact_ref_count"] = len(artifact_refs)
    return stats
