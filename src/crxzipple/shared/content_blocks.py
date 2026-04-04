from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any


TEXT_BLOCK_TYPE = "text"
IMAGE_BLOCK_TYPE = "image"
FILE_BLOCK_TYPE = "file"
IMAGE_REF_BLOCK_TYPE = "image_ref"
FILE_REF_BLOCK_TYPE = "file_ref"


def text_content_block(text: str) -> dict[str, Any]:
    return {"type": TEXT_BLOCK_TYPE, "text": text}


def image_ref_content_block(
    *,
    artifact_id: str,
    mime_type: str,
    name: str | None = None,
    width: int | None = None,
    height: int | None = None,
    preview_url: str | None = None,
    original_url: str | None = None,
) -> dict[str, Any]:
    block: dict[str, Any] = {
        "type": IMAGE_REF_BLOCK_TYPE,
        "artifact_id": artifact_id,
        "mime_type": mime_type,
    }
    if name is not None and name.strip():
        block["name"] = name.strip()
    if isinstance(width, int) and width > 0:
        block["width"] = width
    if isinstance(height, int) and height > 0:
        block["height"] = height
    if isinstance(preview_url, str) and preview_url.strip():
        block["preview_url"] = preview_url.strip()
    if isinstance(original_url, str) and original_url.strip():
        block["original_url"] = original_url.strip()
    return block


def file_ref_content_block(
    *,
    artifact_id: str,
    mime_type: str,
    name: str | None = None,
    download_url: str | None = None,
) -> dict[str, Any]:
    block: dict[str, Any] = {
        "type": FILE_REF_BLOCK_TYPE,
        "artifact_id": artifact_id,
        "mime_type": mime_type,
    }
    if name is not None and name.strip():
        block["name"] = name.strip()
    if isinstance(download_url, str) and download_url.strip():
        block["download_url"] = download_url.strip()
    return block


def is_content_block(value: object) -> bool:
    return isinstance(value, Mapping) and isinstance(value.get("type"), str)


def normalize_content_blocks(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, str):
        if not value.strip():
            return []
        return [text_content_block(value)]
    if is_content_block(value):
        return [_normalize_content_block(value)]
    if isinstance(value, Mapping):
        return normalize_content_blocks(value.get("blocks"))
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        normalized: list[dict[str, Any]] = []
        for item in value:
            if not is_content_block(item):
                raise ValueError("Structured content sequences must contain content blocks.")
            normalized.append(_normalize_content_block(item))
        return normalized
    raise ValueError("Structured content must be a string, content block, or content block sequence.")


def content_blocks_from_payload(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return []
    try:
        blocks = normalize_content_blocks(payload.get("blocks"))
    except ValueError:
        blocks = []
    if blocks:
        return blocks
    try:
        content = normalize_content_blocks(payload.get("content"))
    except ValueError:
        content = []
    if content:
        return content
    text = payload.get("text")
    if isinstance(text, str) and text.strip():
        return [text_content_block(text)]
    return []


def extract_text_content(value: Any) -> str | None:
    blocks = _safe_normalize_content_blocks(value)
    if not blocks:
        return None
    fragments: list[str] = []
    for block in blocks:
        if block.get("type") == TEXT_BLOCK_TYPE:
            text = block.get("text")
            if isinstance(text, str) and text:
                fragments.append(text)
    if not fragments:
        return None
    return "\n".join(fragment for fragment in fragments if fragment)


def describe_content_for_text_fallback(value: Any) -> str:
    blocks = _safe_normalize_content_blocks(value)
    if not blocks:
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    parts: list[str] = []
    for block in blocks:
        block_type = block.get("type")
        if block_type == TEXT_BLOCK_TYPE:
            text = block.get("text")
            if isinstance(text, str) and text:
                parts.append(text)
            continue
        if block_type == IMAGE_BLOCK_TYPE:
            parts.append("[image]")
            continue
        if block_type == IMAGE_REF_BLOCK_TYPE:
            name = block.get("name")
            if isinstance(name, str) and name.strip():
                parts.append(f"[image:{name.strip()}]")
            else:
                parts.append("[image]")
            continue
        if block_type == FILE_BLOCK_TYPE:
            name = block.get("name")
            if isinstance(name, str) and name.strip():
                parts.append(f"[file:{name.strip()}]")
            else:
                parts.append("[file]")
            continue
        if block_type == FILE_REF_BLOCK_TYPE:
            name = block.get("name")
            if isinstance(name, str) and name.strip():
                parts.append(f"[file:{name.strip()}]")
            else:
                parts.append("[file]")
            continue
        parts.append(f"[{block_type}]")
    return "\n".join(parts)


def has_non_text_content_blocks(value: Any) -> bool:
    blocks = _safe_normalize_content_blocks(value)
    return any(block.get("type") != TEXT_BLOCK_TYPE for block in blocks)


def has_image_content_blocks(value: Any) -> bool:
    blocks = _safe_normalize_content_blocks(value)
    return any(
        block.get("type") in {IMAGE_BLOCK_TYPE, IMAGE_REF_BLOCK_TYPE}
        for block in blocks
    )


def has_file_content_blocks(value: Any) -> bool:
    blocks = _safe_normalize_content_blocks(value)
    return any(
        block.get("type") in {FILE_BLOCK_TYPE, FILE_REF_BLOCK_TYPE}
        for block in blocks
    )


def _safe_normalize_content_blocks(value: Any) -> list[dict[str, Any]]:
    try:
        return normalize_content_blocks(value)
    except ValueError:
        return []


def _normalize_content_block(block: Mapping[str, Any]) -> dict[str, Any]:
    block_type = str(block.get("type", "")).strip()
    if block_type == TEXT_BLOCK_TYPE:
        text = block.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Text content blocks require a non-empty 'text' field.")
        return {"type": TEXT_BLOCK_TYPE, "text": text}
    if block_type == IMAGE_BLOCK_TYPE:
        data = block.get("data")
        mime_type = block.get("mime_type", block.get("mimeType"))
        name = block.get("name")
        if not isinstance(data, str) or not data.strip():
            raise ValueError("Image content blocks require a non-empty 'data' field.")
        if not isinstance(mime_type, str) or not mime_type.strip():
            raise ValueError("Image content blocks require a non-empty 'mime_type' field.")
        normalized = {
            "type": IMAGE_BLOCK_TYPE,
            "data": data,
            "mime_type": mime_type,
        }
        if isinstance(name, str) and name.strip():
            normalized["name"] = name.strip()
        return normalized
    if block_type == FILE_BLOCK_TYPE:
        data = block.get("data")
        mime_type = block.get("mime_type", block.get("mimeType"))
        name = block.get("name")
        if not isinstance(data, str) or not data.strip():
            raise ValueError("File content blocks require a non-empty 'data' field.")
        if not isinstance(mime_type, str) or not mime_type.strip():
            raise ValueError("File content blocks require a non-empty 'mime_type' field.")
        normalized: dict[str, Any] = {
            "type": FILE_BLOCK_TYPE,
            "data": data,
            "mime_type": mime_type,
        }
        if isinstance(name, str) and name.strip():
            normalized["name"] = name.strip()
        return normalized
    if block_type == IMAGE_REF_BLOCK_TYPE:
        artifact_id = block.get("artifact_id", block.get("artifactId"))
        mime_type = block.get("mime_type", block.get("mimeType"))
        if not isinstance(artifact_id, str) or not artifact_id.strip():
            raise ValueError(
                "Image ref content blocks require a non-empty 'artifact_id' field.",
            )
        if not isinstance(mime_type, str) or not mime_type.strip():
            raise ValueError(
                "Image ref content blocks require a non-empty 'mime_type' field.",
            )
        normalized = {
            "type": IMAGE_REF_BLOCK_TYPE,
            "artifact_id": artifact_id.strip(),
            "mime_type": mime_type.strip(),
        }
        name = block.get("name")
        if isinstance(name, str) and name.strip():
            normalized["name"] = name.strip()
        width = block.get("width")
        if isinstance(width, int) and width > 0:
            normalized["width"] = width
        height = block.get("height")
        if isinstance(height, int) and height > 0:
            normalized["height"] = height
        preview_url = block.get("preview_url", block.get("previewUrl"))
        if isinstance(preview_url, str) and preview_url.strip():
            normalized["preview_url"] = preview_url.strip()
        original_url = block.get("original_url", block.get("originalUrl"))
        if isinstance(original_url, str) and original_url.strip():
            normalized["original_url"] = original_url.strip()
        return normalized
    if block_type == FILE_REF_BLOCK_TYPE:
        artifact_id = block.get("artifact_id", block.get("artifactId"))
        mime_type = block.get("mime_type", block.get("mimeType"))
        if not isinstance(artifact_id, str) or not artifact_id.strip():
            raise ValueError(
                "File ref content blocks require a non-empty 'artifact_id' field.",
            )
        if not isinstance(mime_type, str) or not mime_type.strip():
            raise ValueError(
                "File ref content blocks require a non-empty 'mime_type' field.",
            )
        normalized = {
            "type": FILE_REF_BLOCK_TYPE,
            "artifact_id": artifact_id.strip(),
            "mime_type": mime_type.strip(),
        }
        name = block.get("name")
        if isinstance(name, str) and name.strip():
            normalized["name"] = name.strip()
        download_url = block.get("download_url", block.get("downloadUrl"))
        if isinstance(download_url, str) and download_url.strip():
            normalized["download_url"] = download_url.strip()
        return normalized
    raise ValueError(f"Unsupported content block type '{block_type}'.")
