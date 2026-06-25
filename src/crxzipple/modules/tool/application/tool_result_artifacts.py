from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from crxzipple.modules.tool.application.ports.artifact import ToolArtifactWritePort
from crxzipple.modules.tool.application.result_envelope import (
    TOOL_RESULT_ENVELOPE_METADATA_KEY,
    TOOL_RESULT_RAW_OUTPUT_BLOCKS_METADATA_KEY,
    ToolResultEnvelope,
)
from crxzipple.modules.tool.application.service_support import (
    decode_tool_attachment_bytes,
)
from crxzipple.modules.tool.domain.entities import Tool
from crxzipple.modules.tool.domain.value_objects import ToolRunResult
from crxzipple.shared.content_blocks import (
    FILE_BLOCK_TYPE,
    IMAGE_BLOCK_TYPE,
    TEXT_BLOCK_TYPE,
    file_ref_content_block,
    image_ref_content_block,
    text_content_block,
)

LARGE_TEXT_RESULT_ARTIFACT_THRESHOLD_CHARS = 20_000
LARGE_TEXT_RESULT_PREVIEW_CHARS = 1_600


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
    raw_output_artifacts = _externalize_raw_output_blocks(
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
            externalized = _externalize_large_text_block(
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
                _externalize_image_block(block, artifact_service=artifact_service),
            )
            changed = True
            continue
        if block_type == FILE_BLOCK_TYPE:
            transformed_blocks.append(
                _externalize_file_block(block, artifact_service=artifact_service),
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
        artifact_envelope = _artifact_result_envelope(
            large_text_artifacts=large_text_artifacts,
            raw_output_artifacts=raw_output_artifacts,
        ).to_payload()
        metadata[TOOL_RESULT_ENVELOPE_METADATA_KEY] = _merge_tool_result_envelopes(
            metadata.get(TOOL_RESULT_ENVELOPE_METADATA_KEY),
            artifact_envelope,
        )
    return ToolRunResult(
        content=transformed_blocks,
        details=result.details,
        metadata=metadata,
    )


def _externalize_raw_output_blocks(
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
        artifact_name = _raw_output_artifact_name(
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


def _externalize_large_text_block(
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
    name = _large_text_artifact_name(tool=tool, block_index=block_index)
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


def _externalize_image_block(
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


def _externalize_file_block(
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


def _large_text_artifact_name(*, tool: Tool, block_index: int) -> str:
    base = tool.id or tool.name or "tool-result"
    normalized = "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "-"
        for char in base.strip()
    ).strip("-.")
    return f"{(normalized or 'tool-result')[:96]}-result-{block_index + 1}.txt"


def _raw_output_artifact_name(
    *,
    tool: Tool,
    stream_name: str,
    block_index: int,
) -> str:
    base = tool.id or tool.name or "tool-result"
    suffix = stream_name or f"raw-{block_index + 1}"
    normalized_base = "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "-"
        for char in base.strip()
    ).strip("-.")
    normalized_suffix = "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "-"
        for char in suffix.strip()
    ).strip("-.")
    return (
        f"{(normalized_base or 'tool-result')[:80]}"
        f"-{(normalized_suffix or 'raw')[:32]}-{block_index + 1}.txt"
    )


def _artifact_result_envelope(
    *,
    large_text_artifacts: list[dict[str, Any]],
    raw_output_artifacts: list[dict[str, Any]],
) -> ToolResultEnvelope:
    artifacts = [*large_text_artifacts, *raw_output_artifacts]
    evidence_refs = tuple(
        str(item["artifact_id"])
        for item in artifacts
        if str(item.get("artifact_id") or "").strip()
    )
    omitted_chars = sum(int(item.get("omitted_chars") or 0) for item in artifacts)
    original_chars = sum(
        int(item.get("original_text_chars") or 0)
        for item in artifacts
    )
    return ToolResultEnvelope(
        status="ok",
        summary=_artifact_result_summary(
            large_text_artifacts=large_text_artifacts,
            raw_output_artifacts=raw_output_artifacts,
        ),
        output_payload={
            "externalized": True,
            "artifact_count": len(evidence_refs),
        },
        artifact_refs=tuple(
            {
                "kind": "artifact",
                "artifact_id": item.get("artifact_id"),
                "mime_type": item.get("mime_type"),
                "name": item.get("name"),
            }
            for item in artifacts
        ),
        key_facts={
            "externalized_text_block_count": len(large_text_artifacts),
            "externalized_raw_output_block_count": len(raw_output_artifacts),
            "artifact_count": len(evidence_refs),
            "original_text_chars": original_chars,
        },
        evidence_refs=evidence_refs,
        read_handles=tuple(
            {
                "kind": "artifact",
                "artifact_id": item.get("artifact_id"),
                "mime_type": item.get("mime_type"),
                "name": item.get("name"),
            }
            for item in artifacts
        ),
        omitted_count=len(artifacts),
        omitted_chars=omitted_chars,
        truncated=True,
        provider_replay_payload={
            "summary": _artifact_result_summary(
                large_text_artifacts=large_text_artifacts,
                raw_output_artifacts=raw_output_artifacts,
            ),
            "artifact_refs": list(evidence_refs),
            "read_handles": [
                {"kind": "artifact", "artifact_id": artifact_id}
                for artifact_id in evidence_refs
            ],
        },
        user_summary_payload={
            "summary": _artifact_result_summary(
                large_text_artifacts=large_text_artifacts,
                raw_output_artifacts=raw_output_artifacts,
            ),
            "artifact_count": len(evidence_refs),
        },
        trace_payload={
            "externalized_text_artifacts": large_text_artifacts,
            "externalized_raw_output_artifacts": raw_output_artifacts,
        },
    )


def _merge_tool_result_envelopes(
    existing: Any,
    artifact_envelope: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(existing, Mapping) or not existing:
        return dict(artifact_envelope)
    merged = dict(existing)
    artifact_payload = dict(artifact_envelope)
    for key in (
        "artifact_refs",
        "evidence_refs",
        "warnings",
    ):
        merged[key] = _merged_json_list(merged.get(key), artifact_payload.get(key))
    artifact_read_handles = _json_list(artifact_payload.get("read_handles"))
    if artifact_read_handles:
        merged["read_handles"] = artifact_read_handles
    else:
        merged["read_handles"] = _merged_json_list(
            merged.get("read_handles"),
            artifact_payload.get("read_handles"),
        )
    for key in ("output_payload", "key_facts", "trace_payload"):
        merged[key] = _merged_json_mapping(
            merged.get(key),
            artifact_payload.get(key),
        )
    merged["provider_replay_payload"] = _merged_provider_replay_payload(
        merged.get("provider_replay_payload"),
        artifact_payload.get("provider_replay_payload"),
    )
    merged["user_summary_payload"] = _merged_json_mapping(
        merged.get("user_summary_payload"),
        artifact_payload.get("user_summary_payload"),
    )
    merged["omitted_count"] = int(merged.get("omitted_count") or 0) + int(
        artifact_payload.get("omitted_count") or 0,
    )
    merged["omitted_chars"] = int(merged.get("omitted_chars") or 0) + int(
        artifact_payload.get("omitted_chars") or 0,
    )
    merged["truncated"] = bool(merged.get("truncated")) or bool(
        artifact_payload.get("truncated"),
    )
    artifact_summary = artifact_payload.get("summary")
    if isinstance(artifact_summary, str) and artifact_summary.strip():
        warnings = _merged_json_list(
            merged.get("warnings"),
            [artifact_summary.strip()],
        )
        if warnings:
            merged["warnings"] = warnings
    return {
        key: value
        for key, value in merged.items()
        if value not in (None, {}, [], ())
    }


def _merged_json_mapping(first: Any, second: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(first, Mapping):
        merged.update(dict(first))
    if isinstance(second, Mapping):
        merged.update(dict(second))
    return merged


def _merged_provider_replay_payload(first: Any, second: Any) -> dict[str, Any]:
    merged = _merged_json_mapping(first, second)
    if isinstance(first, Mapping) and "summary" in first:
        merged["summary"] = first["summary"]
    read_handles = _merged_json_list(
        first.get("read_handles") if isinstance(first, Mapping) else None,
        second.get("read_handles") if isinstance(second, Mapping) else None,
    )
    second_read_handles = (
        _json_list(second.get("read_handles")) if isinstance(second, Mapping) else []
    )
    if second_read_handles:
        read_handles = second_read_handles
    if read_handles:
        merged["read_handles"] = read_handles
    artifact_refs = _merged_json_list(
        first.get("artifact_refs") if isinstance(first, Mapping) else None,
        second.get("artifact_refs") if isinstance(second, Mapping) else None,
    )
    if artifact_refs:
        merged["artifact_refs"] = artifact_refs
    return merged


def _merged_json_list(first: Any, second: Any) -> list[Any]:
    merged: list[Any] = []
    seen: set[str] = set()
    for value in (*_json_list(first), *_json_list(second)):
        marker = json.dumps(value, ensure_ascii=True, sort_keys=True)
        if marker in seen:
            continue
        seen.add(marker)
        merged.append(value)
    return merged


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return []


def _artifact_result_summary(
    *,
    large_text_artifacts: list[dict[str, Any]],
    raw_output_artifacts: list[dict[str, Any]],
) -> str:
    if large_text_artifacts and raw_output_artifacts:
        return "Tool result text and raw output were externalized to artifact refs."
    if raw_output_artifacts:
        return "Tool raw output was externalized to artifact refs."
    return "Large text tool result was externalized to artifact refs."
