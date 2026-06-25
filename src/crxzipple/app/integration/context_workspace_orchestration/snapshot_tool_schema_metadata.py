"""Tool schema mirror metadata for Context Workspace snapshots."""

from __future__ import annotations

from ._metadata import metadata_dict, metadata_int, metadata_text
from .snapshot_metadata_values import metadata_dict_list
from .snapshot_provider_attachments import mirrored_schema_estimated_tokens


def build_snapshot_tool_schema_metadata(
    *,
    provider_attachments: dict[str, object],
    provider_attachment_report: dict[str, object],
    tool_schema_count: int,
) -> dict[str, object]:
    tool_schema_budget = metadata_dict(
        provider_attachment_report.get("tool_schema_mirror_budget"),
    )
    mirrored_schema_tokens = mirrored_schema_estimated_tokens(provider_attachments)
    return {
        "mirrored_tool_schema_count": tool_schema_count,
        "mirrored_tool_schema_estimated_tokens": mirrored_schema_tokens,
        "tool_schema_mirror_budget": dict(tool_schema_budget),
        "tool_schema_mirror_budget_status": (
            metadata_text(tool_schema_budget.get("status")) or "ok"
        ),
        "tool_schema_mirror_default_schema_source": metadata_text(
            tool_schema_budget.get("default_schema_source"),
        ),
        "tool_schema_mirror_available_count": metadata_int(
            tool_schema_budget,
            "available_count",
        ),
        "tool_schema_mirror_enabled_candidate_count": metadata_int(
            tool_schema_budget,
            "enabled_candidate_count",
        ),
        "tool_schema_mirror_default_requested_count": metadata_int(
            tool_schema_budget,
            "default_requested_count",
        ),
        "tool_schema_mirror_default_candidate_count": metadata_int(
            tool_schema_budget,
            "default_candidate_count",
        ),
        "tool_schema_mirror_default_mirrored_count": metadata_int(
            tool_schema_budget,
            "default_mirrored_count",
        ),
        "tool_schema_mirror_duplicate_count": metadata_int(
            tool_schema_budget,
            "duplicate_count",
        ),
        "tool_schema_mirror_groups": metadata_dict_list(
            tool_schema_budget.get("groups"),
        ),
        "tool_schema_mirror_group_count": metadata_int(
            tool_schema_budget,
            "group_count",
        ),
        "tool_schema_mirror_visible_group_count": metadata_int(
            tool_schema_budget,
            "visible_group_count",
        ),
        "tool_schema_mirror_collapsed_group_count": metadata_int(
            tool_schema_budget,
            "collapsed_group_count",
        ),
        "tool_schema_mirror_default_group_count": metadata_int(
            tool_schema_budget,
            "default_group_count",
        ),
        "tool_schema_mirror_default_group_refs": metadata_dict_list(
            tool_schema_budget.get("default_group_refs"),
        ),
        "tool_schema_mirror_default_group_ref_count": metadata_int(
            tool_schema_budget,
            "default_group_ref_count",
        ),
        "tool_schema_mirror_default_group_matches": metadata_dict_list(
            tool_schema_budget.get("default_group_matches"),
        ),
        "tool_schema_mirror_default_group_match_count": metadata_int(
            tool_schema_budget,
            "default_group_match_count",
        ),
        "tool_schema_mirror_default_schema_priorities": metadata_dict(
            tool_schema_budget.get("default_schema_priorities"),
        ),
        "tool_schema_mirror_default_schema_reasons": metadata_dict(
            tool_schema_budget.get("default_schema_reasons"),
        ),
        "tool_schema_mirror_default_mirrored": metadata_dict_list(
            tool_schema_budget.get("default_mirrored"),
        ),
        "tool_schema_mirror_skipped": metadata_dict_list(
            tool_schema_budget.get("skipped"),
        ),
        "tool_schema_mirror_skipped_by_reason": metadata_dict(
            tool_schema_budget.get("skipped_by_reason"),
        ),
        "tool_schema_mirror_skipped_count": metadata_int(
            tool_schema_budget,
            "skipped_count",
        ),
        "tool_schema_mirror_max_count": metadata_int(
            tool_schema_budget,
            "max_count",
        ),
        "tool_schema_mirror_max_estimated_tokens": metadata_int(
            tool_schema_budget,
            "max_estimated_tokens",
        ),
    }
