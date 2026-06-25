"""Context snapshot persistence for request-render snapshots."""

from __future__ import annotations

from crxzipple.modules.context_workspace.application import (
    ContextObservationSnapshotService,
    RecordContextSnapshotInput,
)
from crxzipple.modules.context_workspace.domain import ContextEstimate

from .request_render_input_selection import RequestRenderInputSelection
from .request_render_slice_projection import RequestRenderSliceProjection


def record_request_render_context_snapshot(
    *,
    render_service: ContextObservationSnapshotService,
    session_key: str,
    run_id: str,
    estimate: ContextEstimate,
    slice_projection: RequestRenderSliceProjection,
    input_selection: RequestRenderInputSelection,
    provider_attachments: dict[str, object],
    metadata: dict[str, object],
) -> object:
    return render_service.record_snapshot(
        RecordContextSnapshotInput(
            session_key=session_key,
            run_id=run_id,
            debug_body="",
            provider_attachments=provider_attachments,
            estimate=estimate,
            included_node_ids=slice_projection.included_node_ids,
            mirrored_node_ids=(),
            included_refs=slice_projection.included_refs,
            collapsed_refs=slice_projection.collapsed_refs,
            protocol_required_refs=input_selection.protocol_required_refs,
            metadata=metadata,
            include_metadata_defaults=False,
        ),
    )
