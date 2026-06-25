from __future__ import annotations

from crxzipple.app.integration.context_workspace_session_content_values import (
    optional_text,
)
from crxzipple.modules.session.domain import SessionItem
from crxzipple.shared.content_blocks import (
    FILE_BLOCK_TYPE,
    FILE_REF_BLOCK_TYPE,
    IMAGE_BLOCK_TYPE,
    IMAGE_REF_BLOCK_TYPE,
    TEXT_BLOCK_TYPE,
    content_blocks_from_payload,
)


def blocks_prompt_content(blocks: list[dict[str, object]]) -> str:
    if not blocks:
        return ""
    lines = []
    for block in blocks:
        line = _block_prompt_line(block)
        if line:
            lines.append(line)
    return "\n".join(lines)


def content_block_types(message: SessionItem) -> list[str]:
    return [
        str(block.get("type") or "").strip()
        for block in content_blocks_from_payload(message.content_payload)
        if str(block.get("type") or "").strip()
    ]


def artifact_content_candidates(
    message: SessionItem,
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for index, block in enumerate(content_blocks_from_payload(message.content_payload)):
        artifact_id = optional_text(block.get("artifact_id"))
        mime_type = optional_text(block.get("mime_type"))
        if artifact_id is None or mime_type is None:
            continue
        block_type = str(block.get("type") or "").strip()
        if block_type in {IMAGE_BLOCK_TYPE, IMAGE_REF_BLOCK_TYPE}:
            kind = "artifact_image"
        elif block_type in {FILE_BLOCK_TYPE, FILE_REF_BLOCK_TYPE}:
            kind = "artifact_file"
        elif mime_type.lower().startswith("image/"):
            kind = "artifact_image"
        else:
            kind = "artifact_file"
        candidate: dict[str, object] = {
            "node_id": f"{message.id}.artifact.{index}",
            "artifact_id": artifact_id,
            "kind": kind,
            "mime_type": mime_type,
        }
        name = optional_text(block.get("name"))
        if name is not None:
            candidate["name"] = name
        candidates.append(candidate)
    return candidates


def _block_prompt_line(block: dict[str, object]) -> str:
    block_type = str(block.get("type") or "").strip()
    if block_type == TEXT_BLOCK_TYPE:
        text = block.get("text")
        return text if isinstance(text, str) else ""
    if block_type in {IMAGE_BLOCK_TYPE, IMAGE_REF_BLOCK_TYPE}:
        return _attachment_prompt_line("image", block)
    if block_type in {FILE_BLOCK_TYPE, FILE_REF_BLOCK_TYPE}:
        return _attachment_prompt_line("file", block)
    if block_type:
        return f"[{block_type}]"
    return ""


def _attachment_prompt_line(label: str, block: dict[str, object]) -> str:
    name = optional_text(block.get("name"))
    artifact_id = optional_text(block.get("artifact_id"))
    if name is not None:
        return f"[{label}:{name}]"
    if artifact_id is not None:
        return f"[{label}:{artifact_id}]"
    return f"[{label}]"
