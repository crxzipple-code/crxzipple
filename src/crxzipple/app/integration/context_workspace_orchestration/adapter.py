"""Orchestration to Context Workspace integration."""

from __future__ import annotations

from crxzipple.modules.context_workspace.application import (
    ContextObservationSnapshotService,
    ContextTreeService,
    ContextWorkspaceService,
    RequestRenderSnapshotService,
)
from crxzipple.modules.context_workspace.application.ports import (
    ContextControlSliceBuilder,
    ContextSliceBuilder,
)
from crxzipple.modules.context_workspace.domain import ContextSnapshotNotFoundError
from crxzipple.modules.orchestration.application.ports import (
    RequestRenderSnapshotRecord,
)
from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
    RuntimeLlmRequestDraft,
)
from crxzipple.modules.orchestration.domain import OrchestrationRun

from .artifact_mirror import ArtifactMirrorAdapter
from .recorded_request_render_snapshot_loader import (
    RecordedRequestRenderSnapshotLoader,
)
from .request_render_snapshot_pipeline import RequestRenderSnapshotPipeline
from .request_render_snapshot_recorder import RequestRenderSnapshotRecorder
from .run_workspace_binding import RunWorkspaceBindingAdapter
from .tool_schema_bootstrap import ToolRuntimeRequestCatalog
from .tool_schema_mirror import ToolSchemaMirrorAdapter


class ContextWorkspaceRunSnapshotAdapter:
    """Records request-render snapshots for orchestration runs."""

    def __init__(
        self,
        *,
        workspace_service: ContextWorkspaceService,
        render_service: ContextObservationSnapshotService,
        tree_service: ContextTreeService | None = None,
        slice_builder: ContextSliceBuilder | None = None,
        control_slice_builder: ContextControlSliceBuilder | None = None,
        request_render_snapshot_service: RequestRenderSnapshotService | None = None,
        runtime_request_catalog: ToolRuntimeRequestCatalog | None = None,
        artifact_service: object | None = None,
    ) -> None:
        self._render_service = render_service
        self._request_render_snapshot_recorder = RequestRenderSnapshotRecorder(
            request_render_snapshot_service,
        )
        artifact_mirror_adapter = ArtifactMirrorAdapter(artifact_service)
        self._recorded_request_render_snapshot_loader = (
            RecordedRequestRenderSnapshotLoader(
                request_render_snapshot_recorder=self._request_render_snapshot_recorder,
                artifact_mirror_adapter=artifact_mirror_adapter,
            )
        )
        workspace_binding_adapter = RunWorkspaceBindingAdapter(workspace_service)
        tool_schema_mirror_adapter = ToolSchemaMirrorAdapter(
            tree_service=tree_service,
            runtime_request_catalog=runtime_request_catalog,
        )
        self._request_render_snapshot_pipeline = RequestRenderSnapshotPipeline(
            workspace_binding_adapter=workspace_binding_adapter,
            render_service=self._render_service,
            tool_schema_mirror_adapter=tool_schema_mirror_adapter,
            request_render_snapshot_recorder=self._request_render_snapshot_recorder,
            slice_builder=slice_builder,
            control_slice_builder=control_slice_builder,
        )

    def preview_run_request_render_snapshot(
        self,
        *,
        run: OrchestrationRun,
        draft: RuntimeLlmRequestDraft,
    ) -> RequestRenderSnapshotRecord | None:
        return self._request_render_snapshot_pipeline.record(
            run=run,
            draft=draft,
            persist=False,
        )

    def get_recorded_run_request_render_snapshot(
        self,
        *,
        run: OrchestrationRun,
        draft: RuntimeLlmRequestDraft,
    ) -> RequestRenderSnapshotRecord | None:
        try:
            snapshot = self._render_service.get_snapshot_by_run(run.id)
        except ContextSnapshotNotFoundError:
            return None
        if snapshot.metadata.get("snapshot_kind") != "request_render":
            return None
        if not self._request_render_snapshot_recorder.has_snapshot(snapshot.id):
            return None
        return self._recorded_request_render_snapshot_loader.load(
            snapshot,
            draft=draft,
        )

    def record_run_request_render_snapshot(
        self,
        *,
        run: OrchestrationRun,
        draft: RuntimeLlmRequestDraft,
    ) -> RequestRenderSnapshotRecord | None:
        return self._request_render_snapshot_pipeline.record(
            run=run,
            draft=draft,
        )


__all__ = ["ContextWorkspaceRunSnapshotAdapter"]
