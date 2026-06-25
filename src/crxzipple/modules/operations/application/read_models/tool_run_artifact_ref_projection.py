from __future__ import annotations

from typing import Any


def result_blocks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    blocks = payload.get("content")
    if not isinstance(blocks, list):
        return []
    return [dict(block) for block in blocks if isinstance(block, dict)]


def artifact_refs_from_metadata(
    metadata: dict[str, Any],
    *,
    artifact_service: Any | None,
) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    artifact_id = metadata.get("artifact_id")
    if isinstance(artifact_id, str) and artifact_id.strip():
        refs.append(
            artifact_ref(
                artifact_id=artifact_id.strip(),
                name=optional_str(metadata.get("name")) or artifact_id.strip(),
                kind=optional_str(metadata.get("kind")) or "artifact",
                mime_type=optional_str(metadata.get("mime_type")) or "-",
                size_bytes=optional_int(metadata.get("size_bytes")),
                width=optional_int(metadata.get("width")),
                height=optional_int(metadata.get("height")),
                preview_url=optional_str(metadata.get("preview_url")),
                download_url=optional_str(metadata.get("download_url")),
                artifact_service=artifact_service,
            ),
        )
    artifact_ids = metadata.get("artifact_ids")
    if isinstance(artifact_ids, list):
        for item in artifact_ids:
            if isinstance(item, str) and item.strip():
                refs.append(
                    artifact_ref(
                        artifact_id=item.strip(),
                        name=item.strip(),
                        kind="artifact",
                        mime_type="-",
                        artifact_service=artifact_service,
                    ),
                )
    artifacts = metadata.get("artifacts")
    if isinstance(artifacts, list):
        for item in artifacts:
            if isinstance(item, dict):
                artifact = artifact_from_mapping(
                    item,
                    artifact_service=artifact_service,
                )
                if artifact is not None:
                    refs.append(artifact)
    return refs


def artifact_from_mapping(
    value: dict[str, Any],
    *,
    artifact_service: Any | None,
) -> dict[str, str] | None:
    artifact_id = optional_str(value.get("artifact_id"))
    if artifact_id is None:
        return None
    block_type = optional_str(value.get("type")) or "artifact"
    if block_type == "image_ref":
        kind = "image"
    elif block_type == "file_ref":
        kind = "file"
    else:
        kind = block_type
    return artifact_ref(
        artifact_id=artifact_id,
        name=optional_str(value.get("name")) or artifact_id,
        kind=kind,
        mime_type=optional_str(value.get("mime_type")) or "-",
        size_bytes=optional_int(value.get("size_bytes")),
        width=optional_int(value.get("width")),
        height=optional_int(value.get("height")),
        preview_url=optional_str(value.get("preview_url")),
        download_url=optional_str(value.get("download_url")),
        artifact_service=artifact_service,
    )


def artifact_ref(
    *,
    artifact_id: str,
    name: str,
    kind: str,
    mime_type: str,
    size_bytes: int | None = None,
    width: int | None = None,
    height: int | None = None,
    preview_url: str | None = None,
    download_url: str | None = None,
    artifact_service: Any | None = None,
) -> dict[str, str]:
    artifact = safe_get_artifact(artifact_service, artifact_id)
    if artifact is not None:
        artifact_kind = getattr(artifact, "kind", kind)
        kind = str(getattr(artifact_kind, "value", artifact_kind) or kind)
        name = optional_str(getattr(artifact, "name", None)) or name
        mime_type = optional_str(getattr(artifact, "mime_type", None)) or mime_type
        size_bytes = optional_int(getattr(artifact, "size_bytes", None))
        width = optional_int(getattr(artifact, "width", None))
        height = optional_int(getattr(artifact, "height", None))
        preview_url = preview_url or (
            f"/artifacts/{artifact_id}/preview" if kind == "image" else None
        )
        download_url = download_url or f"/artifacts/{artifact_id}/download"
    return {
        "artifact_id": artifact_id,
        "name": name,
        "kind": kind,
        "mime_type": mime_type,
        "size": bytes_label(size_bytes),
        "dimensions": dimensions_label(width=width, height=height),
        "preview_url": preview_url or "",
        "download_url": download_url or "",
    }


def safe_get_artifact(artifact_service: Any | None, artifact_id: str) -> Any | None:
    if artifact_service is None or not hasattr(artifact_service, "get_artifact"):
        return None
    try:
        return artifact_service.get_artifact(artifact_id)
    except Exception:  # noqa: BLE001
        return None


def bytes_label(size_bytes: int | None) -> str:
    if size_bytes is None or size_bytes < 0:
        return "-"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    kib = size_bytes / 1024
    if kib < 1024:
        return f"{kib:.1f} KiB"
    return f"{kib / 1024:.1f} MiB"


def dimensions_label(*, width: int | None, height: int | None) -> str:
    if width is None or height is None or width <= 0 or height <= 0:
        return "-"
    return f"{width}x{height}"


def optional_str(value: object | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def optional_int(value: object | None) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return None
    return None
