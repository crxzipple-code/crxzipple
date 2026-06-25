from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.context_workspace_row_helpers import (
    estimate_tokens,
    format_time,
    metadata,
    metadata_int,
    metadata_list,
    short_text,
    text,
)


def filter_snapshots(
    snapshots: tuple[Any, ...],
    search: str,
) -> tuple[Any, ...]:
    if not search:
        return snapshots
    needle = search.lower()
    return tuple(
        snapshot
        for snapshot in snapshots
        if needle
        in " ".join(
            (
                text(getattr(snapshot, "id", "")),
                text(getattr(snapshot, "run_id", "")),
                text(getattr(snapshot, "session_key", "")),
                text(getattr(snapshot, "workspace_id", "")),
            ),
        ).lower()
    )


def snapshot_rows(
    snapshots: tuple[Any, ...],
    search: str,
    limit: int,
) -> tuple[dict[str, str], ...]:
    filtered = filter_snapshots(snapshots, search)
    rows: list[dict[str, str]] = []
    for snapshot in filtered[:limit]:
        snapshot_metadata = metadata(getattr(snapshot, "metadata", None))
        session_item_refs = metadata_list(
            snapshot_metadata,
            "session_item_node_refs",
        )
        rows.append(
            {
                "id": text(getattr(snapshot, "id", "")),
                "run": text(getattr(snapshot, "run_id", "")),
                "session": text(getattr(snapshot, "session_key", "")),
                "revision": str(getattr(snapshot, "tree_revision", "")),
                "history": text(snapshot_metadata.get("history_delivery") or "-"),
                "provider_messages": str(
                    metadata_int(snapshot_metadata, "draft_input_message_count"),
                ),
                "tree_items": str(
                    metadata_int(snapshot_metadata, "tree_session_item_count"),
                ),
                "tool_interactions": str(
                    metadata_int(snapshot_metadata, "tree_tool_interaction_count"),
                ),
                "evidence": str(
                    metadata_int(snapshot_metadata, "tree_evidence_item_count"),
                ),
                "folded": str(metadata_int(snapshot_metadata, "folded_history_node_count")),
                "session_tokens": str(
                    metadata_int(snapshot_metadata, "session_estimated_text_tokens"),
                ),
                "range_warnings": str(
                    metadata_int(snapshot_metadata, "session_range_warning_count"),
                ),
                "range_blocked": str(
                    metadata_int(snapshot_metadata, "session_range_blocked_count"),
                ),
                "range_limited": str(
                    metadata_int(snapshot_metadata, "session_range_limited_count"),
                ),
                "session_refs": str(len(session_item_refs)),
                "current_node": short_text(
                    text(snapshot_metadata.get("current_inbound_node_id")),
                ),
                "included_nodes": str(
                    len(tuple(getattr(snapshot, "included_node_ids", ()))),
                ),
                "mirrored_nodes": str(
                    len(tuple(getattr(snapshot, "mirrored_node_ids", ()))),
                ),
                "tokens": str(estimate_tokens(getattr(snapshot, "estimate", None))),
                "prompt_chars": str(len(text(getattr(snapshot, "debug_body", "")))),
                "created": format_time(getattr(snapshot, "created_at", None)),
            },
        )
    return tuple(rows)


def context_budget_rows(
    snapshots: tuple[Any, ...],
    search: str,
    limit: int,
) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    for snapshot in filter_snapshots(snapshots, search)[:limit]:
        snapshot_metadata = metadata(getattr(snapshot, "metadata", None))
        rows.append(
            {
                "id": text(getattr(snapshot, "id", "")),
                "run": text(getattr(snapshot, "run_id", "")),
                "session": text(getattr(snapshot, "session_key", "")),
                "provider_tokens": str(snapshot_provider_tokens(snapshot)),
                "tree_tokens": str(snapshot_rendered_tokens(snapshot)),
                "draft_input_tokens": str(
                    metadata_int(snapshot_metadata, "draft_input_estimated_tokens"),
                ),
                "schema_tokens": str(
                    metadata_int(snapshot_metadata, "mirrored_tool_schema_estimated_tokens"),
                ),
                "schema_budget_status": text(
                    snapshot_metadata.get("tool_schema_mirror_budget_status") or "ok",
                ),
                "schema_budget_skipped": str(
                    metadata_int(snapshot_metadata, "tool_schema_mirror_skipped_count"),
                ),
                "provider_messages": str(
                    metadata_int(snapshot_metadata, "draft_input_message_count"),
                ),
                "mirrored_schemas": str(
                    len(tuple(getattr(snapshot, "mirrored_node_ids", ()))),
                ),
                "duplicate_risk": "yes"
                if bool(snapshot_metadata.get("duplicate_tool_delivery_risk"))
                else "no",
                "created": format_time(getattr(snapshot, "created_at", None)),
            },
        )
    return tuple(rows)


def snapshot_session_range_risk_count(snapshot: Any) -> int:
    snapshot_metadata = metadata(getattr(snapshot, "metadata", None))
    return (
        metadata_int(snapshot_metadata, "session_range_warning_count")
        + metadata_int(snapshot_metadata, "session_range_blocked_count")
        + metadata_int(snapshot_metadata, "session_range_limited_count")
    )


def snapshot_provider_tokens(snapshot: Any) -> int:
    snapshot_metadata = metadata(getattr(snapshot, "metadata", None))
    value = metadata_int(snapshot_metadata, "estimated_provider_input_tokens")
    if value:
        return value
    return estimate_tokens(getattr(snapshot, "estimate", None))


def snapshot_rendered_tokens(snapshot: Any) -> int:
    snapshot_metadata = metadata(getattr(snapshot, "metadata", None))
    value = metadata_int(snapshot_metadata, "debug_body_estimated_tokens")
    if value:
        return value
    rendered_estimate = snapshot_metadata.get("debug_body_estimate")
    if isinstance(rendered_estimate, dict):
        return metadata_int(rendered_estimate, "text_tokens")
    return estimate_tokens(getattr(snapshot, "estimate", None))
