from __future__ import annotations

from crxzipple.modules.workbench.application import view_models as models
import json
from typing import Any

from crxzipple.modules.tool.domain import ToolRun
from crxzipple.modules.tool.domain.value_objects import ToolRunStatus
from crxzipple.modules.workbench.application.projection_helpers import (
    metadata_dict,
    optional_int,
    optional_positive_int,
    optional_text,
    optional_url,
    truncate,
)


TERMINAL_TOOL_RUN_STATUSES = {
    ToolRunStatus.SUCCEEDED,
    ToolRunStatus.FAILED,
    ToolRunStatus.CANCELLED,
    ToolRunStatus.TIMED_OUT,
}

FAILED_TOOL_RUN_STATUSES = {
    ToolRunStatus.FAILED,
    ToolRunStatus.CANCELLED,
    ToolRunStatus.TIMED_OUT,
}


def tool_status(tool_run: ToolRun) -> str:
    if tool_run.status is ToolRunStatus.SUCCEEDED:
        return "success"
    if tool_run.status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}:
        return "failed"
    if tool_run.status is ToolRunStatus.CANCELLED:
        return "cancelled"
    if tool_run.status in {
        ToolRunStatus.RUNNING,
        ToolRunStatus.DISPATCHING,
        ToolRunStatus.CANCEL_REQUESTED,
    }:
        return "running"
    if tool_run.status in {ToolRunStatus.CREATED, ToolRunStatus.QUEUED}:
        return "queued"
    return "unknown"


def tool_badge_tone(tool_run: ToolRun) -> str:
    if tool_run.status is ToolRunStatus.SUCCEEDED:
        return "success"
    if tool_run.status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}:
        return "danger"
    if tool_run.status in {ToolRunStatus.CANCELLED, ToolRunStatus.CANCEL_REQUESTED}:
        return "warning"
    return "info"


def tool_call_summary(tool_run: ToolRun | None) -> str:
    if tool_run is None:
        return "Waiting for pending tool runs to finish."
    return f"{tool_run.tool_id} · {compact_payload(tool_run.input_payload, limit=180)}"


def tool_step_summary(tool_run: ToolRun) -> str:
    lines = [
        f"Request: {compact_payload(tool_run.input_payload, limit=180)}",
    ]
    if tool_run.status in TERMINAL_TOOL_RUN_STATUSES:
        lines.append(f"Result: {truncate(tool_result_summary(tool_run), limit=260)}")
    else:
        lines.append(f"Status: {tool_run.status.value}")
    return "\n".join(lines)


def tool_result_summary(tool_run: ToolRun) -> str:
    if tool_run.status is not ToolRunStatus.SUCCEEDED:
        error = tool_run.error
        if error is not None:
            return error.message
        return f"Tool run {tool_run.status.value}."
    result = tool_run.result
    if result is None:
        return "Tool completed."
    for block in result.blocks:
        if block.get("type") == "text":
            text = str(block.get("text") or "").strip()
            if text:
                return text
    return "Tool completed."


def tool_artifacts(
    tool_run: ToolRun,
    *,
    artifact_query: Any | None = None,
) -> tuple[Any, ...]:
    result = tool_run.result
    if result is None:
        return ()
    previews: list[Any] = []
    for block in result.blocks:
        block_type = str(block.get("type") or "")
        if block_type not in {"image_ref", "file_ref"}:
            continue
        artifact_id = str(block.get("artifact_id") or "").strip()
        if not artifact_id:
            continue
        name = str(block.get("name") or artifact_id).strip() or artifact_id
        kind = "image" if block_type == "image_ref" else "file"
        artifact = safe_get_artifact(artifact_query, artifact_id)
        previews.append(
            artifact_preview_from_block(
                block,
                artifact=artifact,
                fallback_name=name,
                fallback_kind=kind,
            ),
        )
    return tuple(previews)


def artifact_preview_from_block(
    block: dict[str, Any],
    *,
    artifact: Any | None,
    fallback_name: str,
    fallback_kind: str,
):
    artifact_id = str(block.get("artifact_id") or "").strip()
    if artifact is None:
        return models.ArtifactPreview(
            artifact_id=artifact_id,
            name=fallback_name,
            kind=fallback_kind,
            size_bytes=optional_int(block.get("size_bytes")),
            mime_type=optional_text(block.get("mime_type")),
            width=optional_positive_int(block.get("width")),
            height=optional_positive_int(block.get("height")),
            preview_url=optional_url(block.get("preview_url"))
            or (
                f"/artifacts/{artifact_id}/preview"
                if fallback_kind == "image"
                else None
            ),
            download_url=optional_url(block.get("download_url"))
            or f"/artifacts/{artifact_id}/download",
        )
    kind = getattr(artifact, "kind", fallback_kind)
    kind_value = getattr(kind, "value", kind)
    normalized_kind = str(kind_value or fallback_kind)
    name = optional_text(getattr(artifact, "name", None)) or fallback_name
    return models.ArtifactPreview(
        artifact_id=artifact_id,
        name=name,
        kind=normalized_kind,
        size_bytes=optional_int(getattr(artifact, "size_bytes", None)),
        mime_type=optional_text(getattr(artifact, "mime_type", None))
        or optional_text(block.get("mime_type")),
        width=optional_positive_int(getattr(artifact, "width", None))
        or optional_positive_int(block.get("width")),
        height=optional_positive_int(getattr(artifact, "height", None))
        or optional_positive_int(block.get("height")),
        preview_url=optional_url(block.get("preview_url"))
        or (
            f"/artifacts/{artifact_id}/preview"
            if normalized_kind == "image"
            else None
        ),
        download_url=optional_url(block.get("download_url"))
        or f"/artifacts/{artifact_id}/download",
        metadata=metadata_dict(getattr(artifact, "metadata", None)),
    )


def cover_artifact(
    tool_runs: tuple[ToolRun, ...],
    *,
    artifact_query: Any | None,
):
    for tool_run in sorted(
        tool_runs,
        key=lambda item: item.completed_at or item.started_at or item.created_at,
        reverse=True,
    ):
        if tool_run.status not in TERMINAL_TOOL_RUN_STATUSES:
            continue
        for artifact in tool_artifacts(tool_run, artifact_query=artifact_query):
            if artifact.kind == "image":
                return artifact
    return None


def safe_get_artifact(
    artifact_query: Any | None,
    artifact_id: str,
) -> Any | None:
    if artifact_query is None:
        return None
    try:
        return artifact_query.get_artifact(artifact_id)
    except Exception:
        return None


def compact_payload(value: Any, *, limit: int) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        text = str(value)
    return text if len(text) <= limit else f"{text[: limit - 3]}..."
