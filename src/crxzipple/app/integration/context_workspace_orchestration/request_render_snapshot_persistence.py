"""Request-render snapshot persistence payload helpers."""

from __future__ import annotations

from crxzipple.modules.context_workspace.domain import ContextEstimate

from .request_render_slice_projection import RequestRenderSliceProjection
from .request_render_snapshot_recorder import RequestRenderSnapshotRecorder


def record_request_render_snapshot_if_available(
    *,
    recorder: RequestRenderSnapshotRecorder,
    context_snapshot_id: str,
    workspace_id: str,
    session_key: str,
    run_id: str,
    tree_revision: int,
    model: str,
    slice_projection: RequestRenderSliceProjection,
    visible_tool_schema_refs: tuple[dict[str, object], ...],
    estimate: ContextEstimate,
    request_render_report: dict[str, object],
    timings: dict[str, float],
    metadata: dict[str, object],
) -> str:
    if not recorder.available:
        return context_snapshot_id
    return recorder.record(
        snapshot_id=context_snapshot_id,
        workspace_id=workspace_id,
        session_key=session_key,
        run_id=run_id,
        tree_revision=tree_revision,
        model=model,
        input_item_refs=slice_projection.included_refs,
        projected_input_items=slice_projection.projected_input_items,
        tool_schema_refs=visible_tool_schema_refs,
        resource_refs=slice_projection.collapsed_refs,
        estimated_tokens=estimate.text_tokens,
        render_report={
            **request_render_report,
            "timings": dict(timings),
        },
        timings=timings,
        metadata=metadata,
    )
