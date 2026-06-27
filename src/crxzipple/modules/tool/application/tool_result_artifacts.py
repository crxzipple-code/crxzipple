from __future__ import annotations

from typing import Any

from crxzipple.modules.tool.application.tool_result_artifact_envelopes import (
    artifact_result_envelope,
    merge_tool_result_envelopes,
)
from crxzipple.modules.tool.application.tool_result_artifact_externalization import (
    externalize_file_block,
    externalize_image_block,
    externalize_large_text_block,
    externalize_raw_output_blocks,
)
from crxzipple.modules.tool.application.ports.artifact import ToolArtifactWritePort
from crxzipple.modules.tool.application.result_envelope import (
    TOOL_RESULT_ENVELOPE_METADATA_KEY,
    TOOL_RESULT_RAW_OUTPUT_BLOCKS_METADATA_KEY,
)
from crxzipple.modules.tool.domain.entities import Tool
from crxzipple.modules.tool.domain.value_objects import ToolRunResult
from crxzipple.shared.content_blocks import (
    FILE_BLOCK_TYPE,
    IMAGE_BLOCK_TYPE,
    TEXT_BLOCK_TYPE,
)


def externalize_tool_result_attachments(
    result: ToolRunResult,
    *,
    run_id: str,
    tool: Tool,
    artifact_service: ToolArtifactWritePort | None,
) -> ToolRunResult:
    if artifact_service is None:
        return result
    transformed_blocks: list[dict[str, Any]] = []
    metadata = dict(result.metadata)
    large_text_artifacts: list[dict[str, Any]] = []
    raw_output_artifacts = externalize_raw_output_blocks(
        metadata.pop(TOOL_RESULT_RAW_OUTPUT_BLOCKS_METADATA_KEY, None),
        run_id=run_id,
        tool=tool,
        artifact_service=artifact_service,
    )
    artifact_ids: list[str] = [
        str(item).strip()
        for item in metadata.get("artifact_ids", ())
        if str(item).strip()
    ] if isinstance(metadata.get("artifact_ids"), list) else []
    artifact_ids.extend(
        str(item["artifact_id"])
        for item in raw_output_artifacts
        if str(item.get("artifact_id") or "").strip()
    )
    changed = False
    for index, block in enumerate(result.blocks):
        block_type = str(block.get("type") or "").strip()
        if block_type == TEXT_BLOCK_TYPE:
            externalized = externalize_large_text_block(
                block,
                run_id=run_id,
                tool=tool,
                block_index=index,
                artifact_service=artifact_service,
            )
            if externalized is not None:
                transformed_blocks.append(externalized["block"])
                artifact = externalized["artifact"]
                artifact_ids.append(str(artifact["artifact_id"]))
                large_text_artifacts.append(artifact)
                changed = True
                continue
        if block_type == IMAGE_BLOCK_TYPE:
            transformed_blocks.append(
                externalize_image_block(block, artifact_service=artifact_service),
            )
            changed = True
            continue
        if block_type == FILE_BLOCK_TYPE:
            transformed_blocks.append(
                externalize_file_block(block, artifact_service=artifact_service),
            )
            changed = True
            continue
        transformed_blocks.append(dict(block))
    if raw_output_artifacts:
        changed = True
    if not changed:
        return result
    if artifact_ids:
        metadata["artifact_ids"] = list(dict.fromkeys(artifact_ids))
    if large_text_artifacts:
        metadata["large_text_artifact_ids"] = [
            item["artifact_id"] for item in large_text_artifacts
        ]
        metadata["externalized_text_blocks"] = large_text_artifacts
    if raw_output_artifacts:
        metadata["raw_output_artifact_ids"] = [
            item["artifact_id"] for item in raw_output_artifacts
        ]
        metadata["externalized_raw_output_blocks"] = raw_output_artifacts
    if large_text_artifacts or raw_output_artifacts:
        artifact_envelope = artifact_result_envelope(
            large_text_artifacts=large_text_artifacts,
            raw_output_artifacts=raw_output_artifacts,
        ).to_payload()
        metadata[TOOL_RESULT_ENVELOPE_METADATA_KEY] = merge_tool_result_envelopes(
            metadata.get(TOOL_RESULT_ENVELOPE_METADATA_KEY),
            artifact_envelope,
        )
    return ToolRunResult(
        content=transformed_blocks,
        details=result.details,
        metadata=metadata,
    )
