from __future__ import annotations

from typing import Any

from crxzipple.modules.tool.application.ports.artifact import ToolArtifactWritePort
from crxzipple.modules.tool.application.service_support import (
    decode_tool_attachment_bytes,
)
from crxzipple.modules.tool.domain.entities import Tool
from crxzipple.shared.content_blocks import (
    file_ref_content_block,
    image_ref_content_block,
    text_content_block,
)

LARGE_TEXT_RESULT_ARTIFACT_THRESHOLD_CHARS = 20_000
LARGE_TEXT_RESULT_PREVIEW_CHARS = 1_600


def externalize_raw_output_blocks(
    raw_blocks: Any,
    *,
    run_id: str,
    tool: Tool,
    artifact_service: ToolArtifactWritePort,
) -> list[dict[str, Any]]:
    if not isinstance(raw_blocks, list):
        return []
    artifacts: list[dict[str, Any]] = []
    for index, item in enumerate(raw_blocks):
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if not isinstance(text, str) or not text:
            continue
        stream_name = str(item.get("name") or f"raw-{index + 1}").strip()
        encoded = text.encode("utf-8")
        artifact_name = raw_output_artifact_name(
            tool=tool,
            stream_name=stream_name,
            block_index=index,
        )
        artifact = artifact_service.create_artifact(
            data=encoded,
            mime_type=str(item.get("mime_type") or "text/plain"),
            name=artifact_name,
            metadata={
                "source": "tool.raw_output",
                "tool_id": tool.id,
                "tool_name": tool.name,
                "tool_run_id": run_id,
                "raw_output_name": stream_name,
                "raw_output_block_index": index,
                "original_text_chars": len(text),
                "original_text_bytes": len(encoded),
            },
        )
        artifacts.append(
            {
                "artifact_id": artifact.id,
                "mime_type": artifact.mime_type,
                "name": artifact.name,
                "size_bytes": artifact.size_bytes,
                "raw_output_name": stream_name,
                "original_text_chars": len(text),
                "omitted_chars": len(text),
                "content_block_index": None,
            },
        )
    return artifacts


def externalize_large_text_block(
    block: dict[str, Any],
    *,
    run_id: str,
    tool: Tool,
    block_index: int,
    artifact_service: ToolArtifactWritePort,
) -> dict[str, Any] | None:
    text = block.get("text")
    if not isinstance(text, str):
        return None
    if len(text) <= LARGE_TEXT_RESULT_ARTIFACT_THRESHOLD_CHARS:
        return None
    encoded = text.encode("utf-8")
    name = large_text_artifact_name(tool=tool, block_index=block_index)
    artifact = artifact_service.create_artifact(
        data=encoded,
        mime_type="text/plain",
        name=name,
        metadata={
            "source": "tool.large_text_result",
            "tool_id": tool.id,
            "tool_name": tool.name,
            "tool_run_id": run_id,
            "content_block_index": block_index,
            "original_text_chars": len(text),
            "original_text_bytes": len(encoded),
        },
    )
    preview = text[:LARGE_TEXT_RESULT_PREVIEW_CHARS].rstrip()
    omitted_chars = max(len(text) - len(preview), 0)
    summary = (
        "[large tool result externalized]\n"
        f"artifact_id: {artifact.id}\n"
        f"name: {artifact.name or name}\n"
        f"mime_type: {artifact.mime_type}\n"
        f"original_chars: {len(text)}\n"
        f"omitted_chars: {omitted_chars}\n"
        "Use the artifact owner read hint if the full result is needed."
    )
    if preview:
        summary = f"{summary}\n\npreview:\n{preview}"
    return {
        "block": text_content_block(summary),
        "artifact": {
            "artifact_id": artifact.id,
            "mime_type": artifact.mime_type,
            "name": artifact.name,
            "size_bytes": artifact.size_bytes,
            "original_text_chars": len(text),
            "omitted_chars": omitted_chars,
            "content_block_index": block_index,
        },
    }


def externalize_image_block(
    block: dict[str, Any],
    *,
    artifact_service: ToolArtifactWritePort,
) -> dict[str, Any]:
    data = block.get("data")
    mime_type = block.get("mime_type")
    if not isinstance(data, str) or not isinstance(mime_type, str):
        return dict(block)
    decoded = decode_tool_attachment_bytes(data)
    if decoded is None:
        return dict(block)
    name = block.get("name")
    artifact = artifact_service.create_artifact(
        data=decoded,
        mime_type=mime_type,
        name=name if isinstance(name, str) and name.strip() else None,
        metadata={"source": "tool.inline_image"},
    )
    return image_ref_content_block(
        artifact_id=artifact.id,
        mime_type=artifact.mime_type,
        name=artifact.name,
    )


def externalize_file_block(
    block: dict[str, Any],
    *,
    artifact_service: ToolArtifactWritePort,
) -> dict[str, Any]:
    data = block.get("data")
    mime_type = block.get("mime_type")
    if not isinstance(data, str) or not isinstance(mime_type, str):
        return dict(block)
    decoded = decode_tool_attachment_bytes(data)
    if decoded is None:
        return dict(block)
    name = block.get("name")
    artifact = artifact_service.create_artifact(
        data=decoded,
        mime_type=mime_type,
        name=name if isinstance(name, str) and name.strip() else None,
        metadata={"source": "tool.inline_file"},
    )
    return file_ref_content_block(
        artifact_id=artifact.id,
        mime_type=artifact.mime_type,
        name=artifact.name,
    )


def large_text_artifact_name(*, tool: Tool, block_index: int) -> str:
    base = tool.id or tool.name or "tool-result"
    normalized = _safe_artifact_name_part(base)
    return f"{(normalized or 'tool-result')[:96]}-result-{block_index + 1}.txt"


def raw_output_artifact_name(
    *,
    tool: Tool,
    stream_name: str,
    block_index: int,
) -> str:
    base = tool.id or tool.name or "tool-result"
    suffix = stream_name or f"raw-{block_index + 1}"
    normalized_base = _safe_artifact_name_part(base)
    normalized_suffix = _safe_artifact_name_part(suffix)
    return (
        f"{(normalized_base or 'tool-result')[:80]}"
        f"-{(normalized_suffix or 'raw')[:32]}-{block_index + 1}.txt"
    )


def _safe_artifact_name_part(value: str) -> str:
    return "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "-"
        for char in value.strip()
    ).strip("-.")
