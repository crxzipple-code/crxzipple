"""Artifact attachment metadata for Context Workspace snapshots."""

from __future__ import annotations

from ._metadata import metadata_int
from .artifact_mirror import artifact_content_budget


def build_snapshot_artifact_metadata(
    *,
    provider_attachments: dict[str, object],
    artifact_content_blocks: tuple[dict[str, object], ...],
) -> dict[str, object]:
    content_budget = artifact_content_budget(
        provider_attachments=provider_attachments,
        artifact_content_blocks=artifact_content_blocks,
    )
    artifact_content_tokens = metadata_int(
        content_budget,
        "estimated_tokens",
    )
    return {
        "artifact_content_budget": dict(content_budget),
        "artifact_content_estimated_tokens": artifact_content_tokens,
        "artifact_content_candidate_count": metadata_int(
            content_budget,
            "candidate_count",
        ),
        "artifact_content_text_block_count": metadata_int(
            content_budget,
            "text_block_count",
        ),
        "artifact_content_image_count": metadata_int(
            content_budget,
            "image_count",
        ),
        "artifact_content_file_count": metadata_int(
            content_budget,
            "file_count",
        ),
        "artifact_content_omitted_count": metadata_int(
            content_budget,
            "omitted_count",
        ),
        "artifact_content_block_count": len(artifact_content_blocks),
    }
