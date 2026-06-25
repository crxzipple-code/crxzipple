from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crxzipple.modules.llm.application.runtime_request_snapshot import (
    RuntimeLlmRequestRenderSnapshot,
    build_runtime_llm_request_metadata,
    build_runtime_request_render_snapshot,
)
from crxzipple.modules.llm.domain import ToolSchema


def build_llm_request_metadata(
    *,
    draft: Any,
    request_render_snapshot_id: str | None,
    snapshot_metadata: dict[str, object],
    tool_schemas: tuple[ToolSchema, ...],
    run_id: str | None = None,
    agent_id: str | None = None,
    session_key: str | None = None,
    active_session_id: str | None = None,
) -> dict[str, object]:
    provider_tool_schema_names = tuple(
        schema.name for schema in tool_schemas if schema.name.strip()
    )
    metadata = build_runtime_llm_request_metadata(
        runtime_request_mode=mode_value(draft.mode),
        runtime_request_surface=draft.surface_policy.surface,
        request_render_snapshot_id=request_render_snapshot_id,
        snapshot_metadata=snapshot_metadata,
        provider_tool_schema_names=provider_tool_schema_names,
    )
    for key, value in {
        "run_id": run_id,
        "agent_id": agent_id,
        "session_key": session_key,
        "active_session_id": active_session_id,
    }.items():
        text = str(value or "").strip()
        if text:
            metadata[key] = text
    return metadata


def surface_id_from_snapshot_result(result: object) -> str | None:
    raw = getattr(result, "surface_id", None)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if isinstance(result, Mapping):
        raw = result.get("surface_id")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def validation_error(
    message: str,
    *,
    code: str,
    details: dict[str, object],
) -> Exception:
    from crxzipple.modules.orchestration.domain import OrchestrationValidationError

    return OrchestrationValidationError(message, code=code, details=details)


def request_render_snapshot_report(**kwargs: object) -> object:
    from crxzipple.modules.orchestration.application.runtime_request_report import (
        RequestRenderSnapshotReport,
    )

    return RequestRenderSnapshotReport(**kwargs)


def mode_value(mode: object) -> str:
    return str(getattr(mode, "value", mode) or "").strip()


def mode_requires_transcript_input(mode: object) -> bool:
    return mode_value(mode) not in {"heartbeat", "memory_flush", "compaction"}


def request_render_snapshot_from_snapshot(
    snapshot: Any | None,
) -> RuntimeLlmRequestRenderSnapshot:
    if snapshot is None:
        return build_runtime_request_render_snapshot()
    return build_runtime_request_render_snapshot(
        snapshot_id=snapshot.snapshot_id,
        included_node_ids=tuple(snapshot.included_node_ids),
        mirrored_node_ids=tuple(snapshot.mirrored_node_ids),
        included_refs=tuple(dict(item) for item in snapshot.included_refs),
        collapsed_refs=tuple(dict(item) for item in snapshot.collapsed_refs),
        protocol_required_refs=tuple(
            dict(item) for item in snapshot.protocol_required_refs
        ),
        estimate=snapshot.estimate or {},
        metadata=snapshot.metadata,
    )


def runtime_context_metadata(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    allowed_keys = (
        "agent_id",
        "run_id",
        "llm_id",
        "session_key",
        "active_session_id",
        "agent_home_dir",
        "workspace_dir",
        "available_tool_ids",
        "current_step",
        "max_steps",
        "remaining_steps",
        "step_budget_status",
    )
    payload: dict[str, object] = {}
    for key in allowed_keys:
        raw = value.get(key)
        if raw in (None, "", {}, []):
            continue
        if key == "available_tool_ids" and isinstance(raw, (list, tuple)):
            tool_ids = [str(item) for item in raw if str(item).strip()]
            if tool_ids:
                payload[key] = tool_ids
            continue
        payload[key] = raw
    return payload


__all__ = [
    "build_llm_request_metadata",
    "mode_requires_transcript_input",
    "mode_value",
    "request_render_snapshot_from_snapshot",
    "request_render_snapshot_report",
    "runtime_context_metadata",
    "surface_id_from_snapshot_result",
    "validation_error",
]
