"""Artifact provider attachment helpers for orchestration prompt snapshots."""

from __future__ import annotations

import base64

from crxzipple.modules.artifacts.domain.entities import ArtifactVariant
from crxzipple.shared.content_blocks import text_content_block

from ._metadata import estimate_text_tokens


_MAX_LLM_IMAGE_BYTES = 1_500_000
_MAX_LLM_FILE_BYTES = 4_000_000
_MAX_LLM_TEXT_FILE_CHARS = 24_000


def build_artifact_content_blocks(
    provider_attachments: dict[str, object],
    *,
    artifact_service: object | None,
    allow_vision: bool = True,
) -> tuple[dict[str, object], ...]:
    if artifact_service is None:
        return ()
    raw_candidates = provider_attachments.get("artifact_content_candidates")
    if not isinstance(raw_candidates, list):
        return ()
    blocks: list[dict[str, object]] = []
    for raw_candidate in raw_candidates:
        if not isinstance(raw_candidate, dict):
            continue
        artifact_id = raw_candidate.get("artifact_id")
        if not isinstance(artifact_id, str) or not artifact_id.strip():
            continue
        variant = _artifact_variant(raw_candidate)
        try:
            resolved = artifact_service.resolve_variant(artifact_id, variant=variant)
        except Exception:  # noqa: BLE001
            blocks.append(_missing_attachment_block(raw_candidate))
            continue
        try:
            raw_bytes = resolved.path.read_bytes()
        except OSError:
            blocks.append(_missing_attachment_block(raw_candidate))
            continue
        artifact = resolved.artifact
        if str(raw_candidate.get("kind")) == "artifact_image":
            if not allow_vision:
                blocks.append(
                    text_content_block(
                        "[image attachment omitted for non-vision model"
                        f"{_attachment_label(raw_candidate, artifact=artifact)}]",
                    ),
                )
                continue
            if len(raw_bytes) > _MAX_LLM_IMAGE_BYTES:
                blocks.append(
                    text_content_block(
                        "[image attachment omitted - exceeds llm size budget"
                        f"{_attachment_label(raw_candidate, artifact=artifact)}]",
                    ),
                )
                continue
            blocks.append(
                {
                    "type": "image",
                    "mime_type": artifact.mime_type,
                    "data": base64.b64encode(raw_bytes).decode("ascii"),
                },
            )
            continue
        if _is_text_like_file_mime_type(artifact.mime_type):
            decoded = raw_bytes.decode("utf-8", errors="replace")
            if len(decoded) > _MAX_LLM_TEXT_FILE_CHARS:
                decoded = (
                    decoded[:_MAX_LLM_TEXT_FILE_CHARS].rstrip()
                    + "\n\n[file truncated for llm budget]"
                )
            name = artifact.name or raw_candidate.get("name")
            header = (
                f"[file:{name.strip()}]\n"
                if isinstance(name, str) and name.strip()
                else "[file]\n"
            )
            blocks.append(text_content_block(f"{header}{decoded}"))
            continue
        if len(raw_bytes) > _MAX_LLM_FILE_BYTES:
            blocks.append(
                text_content_block(
                    "[file attachment omitted - exceeds llm size budget"
                    f"{_attachment_label(raw_candidate, artifact=artifact)}]",
                ),
            )
            continue
        block: dict[str, object] = {
            "type": "file",
            "mime_type": artifact.mime_type,
            "data": base64.b64encode(raw_bytes).decode("ascii"),
        }
        name = artifact.name or raw_candidate.get("name")
        if isinstance(name, str) and name.strip():
            block["name"] = name.strip()
        blocks.append(block)
    return tuple(blocks)


def artifact_content_budget(
    *,
    provider_attachments: dict[str, object],
    artifact_content_blocks: tuple[dict[str, object], ...],
) -> dict[str, object]:
    raw_candidates = provider_attachments.get("artifact_content_candidates")
    candidate_count = len(raw_candidates) if isinstance(raw_candidates, list) else 0
    text_chars = 0
    text_tokens = 0
    text_block_count = 0
    image_count = 0
    file_count = 0
    omitted_count = 0
    for block in artifact_content_blocks:
        block_type = block.get("type")
        if block_type == "text":
            text = block.get("text")
            if isinstance(text, str):
                text_block_count += 1
                text_chars += len(text)
                text_tokens += estimate_text_tokens(text)
                if "attachment omitted" in text:
                    omitted_count += 1
            continue
        if block_type == "image":
            image_count += 1
            continue
        if block_type == "file":
            file_count += 1
            continue
    return {
        "candidate_count": candidate_count,
        "block_count": len(artifact_content_blocks),
        "provider_attachment_count": len(artifact_content_blocks),
        "text_block_count": text_block_count,
        "text_chars": text_chars,
        "text_tokens": text_tokens,
        "estimated_tokens": text_tokens,
        "image_count": image_count,
        "file_count": file_count,
        "omitted_count": omitted_count,
        "status": "omitted" if omitted_count else "ok",
    }


def _missing_attachment_block(candidate: dict[str, object]) -> dict[str, object]:
    kind = str(candidate.get("kind") or "").strip()
    label = _attachment_label(candidate, artifact=None)
    if kind == "artifact_image":
        return text_content_block(f"[missing image attachment{label}]")
    return text_content_block(f"[missing file attachment{label}]")


def _attachment_label(
    candidate: dict[str, object],
    *,
    artifact: object | None,
) -> str:
    artifact_name = getattr(artifact, "name", None)
    name = artifact_name if isinstance(artifact_name, str) else candidate.get("name")
    if isinstance(name, str) and name.strip():
        return f":{name.strip()}"
    return ""


def _is_text_like_file_mime_type(mime_type: str) -> bool:
    normalized = mime_type.strip().lower()
    return normalized in {
        "text/plain",
        "text/markdown",
        "text/csv",
        "application/json",
        "application/xml",
        "application/yaml",
        "application/x-yaml",
    } or normalized.startswith("text/")


def _artifact_variant(candidate: dict[str, object]) -> ArtifactVariant:
    raw = candidate.get("preferred_variant")
    if not isinstance(raw, str) or not raw.strip():
        raw = "llm" if candidate.get("kind") == "artifact_image" else "original"
    try:
        return ArtifactVariant(raw.strip())
    except ValueError:
        return ArtifactVariant.ORIGINAL
