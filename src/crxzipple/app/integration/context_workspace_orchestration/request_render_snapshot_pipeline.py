from __future__ import annotations

from crxzipple.modules.context_workspace.application import (
    ContextObservationSnapshotService,
    ContextWorkspaceService,
    RequestRenderSnapshotService,
)
from crxzipple.modules.context_workspace.application.ports import (
    ContextControlSliceBuilder,
    ContextSliceBuilder,
)
from crxzipple.modules.context_workspace.domain import ContextEstimate
from crxzipple.modules.orchestration.application.ports import (
    RequestRenderSnapshotRecord,
)
from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
    RuntimeLlmRequestDraft,
)
from crxzipple.modules.orchestration.domain import OrchestrationRun

from .request_render_input_selection import build_request_render_input_selection
from .request_render_context_snapshot import record_request_render_context_snapshot
from .request_render_refs import (
    metadata_string_values,
)
from .request_render_metadata_bundle import build_request_render_metadata_bundle
from .request_render_record import build_request_render_snapshot_record
from .request_render_snapshot_metadata import RequestRenderSnapshotMetadataBuilder
from .request_render_snapshot_persistence import (
    record_request_render_snapshot_if_available,
)
from .request_render_snapshot_recorder import RequestRenderSnapshotRecorder
from .request_render_slice_building import (
    build_request_context_slice,
    build_request_control_slice,
)
from .request_render_slice_projection import project_request_render_slices
from .request_render_timing import (
    attach_request_render_timings,
    elapsed_ms,
    now as timing_now,
    record_timing,
)
from .request_render_tool_selection import (
    requested_tool_schema_names as resolve_requested_tool_schema_names,
    visible_tool_schema_selection,
)
from .run_workspace_binding import RunWorkspaceBindingAdapter
from .request_render_workspace import bind_request_render_workspace
from .tool_schema_mirror import ToolSchemaMirrorAdapter


class RequestRenderSnapshotPipeline:
    def __init__(
        self,
        *,
        workspace_binding_adapter: RunWorkspaceBindingAdapter,
        render_service: ContextObservationSnapshotService,
        tool_schema_mirror_adapter: ToolSchemaMirrorAdapter,
        request_render_snapshot_recorder: RequestRenderSnapshotRecorder,
        request_render_snapshot_metadata_builder: (
            RequestRenderSnapshotMetadataBuilder | None
        ) = None,
        slice_builder: ContextSliceBuilder | None = None,
        control_slice_builder: ContextControlSliceBuilder | None = None,
    ) -> None:
        self._workspace_binding_adapter = workspace_binding_adapter
        self._render_service = render_service
        self._tool_schema_mirror_adapter = tool_schema_mirror_adapter
        self._request_render_snapshot_recorder = request_render_snapshot_recorder
        self._request_render_snapshot_metadata_builder = (
            request_render_snapshot_metadata_builder
            or RequestRenderSnapshotMetadataBuilder()
        )
        self._slice_builder = slice_builder
        self._control_slice_builder = control_slice_builder

    @classmethod
    def from_services(
        cls,
        *,
        workspace_service: ContextWorkspaceService,
        render_service: ContextObservationSnapshotService,
        tool_schema_mirror_adapter: ToolSchemaMirrorAdapter,
        request_render_snapshot_service: RequestRenderSnapshotService | None = None,
        slice_builder: ContextSliceBuilder | None = None,
        control_slice_builder: ContextControlSliceBuilder | None = None,
    ) -> "RequestRenderSnapshotPipeline":
        return cls(
            workspace_binding_adapter=RunWorkspaceBindingAdapter(workspace_service),
            render_service=render_service,
            tool_schema_mirror_adapter=tool_schema_mirror_adapter,
            request_render_snapshot_recorder=RequestRenderSnapshotRecorder(
                request_render_snapshot_service,
            ),
            slice_builder=slice_builder,
            control_slice_builder=control_slice_builder,
        )

    def record(
        self,
        *,
        run: OrchestrationRun,
        draft: RuntimeLlmRequestDraft,
        persist: bool = True,
    ) -> RequestRenderSnapshotRecord | None:
        session_key = draft.session_key.strip()
        agent_id = str(run.agent_id or "").strip()
        if not session_key or not agent_id:
            return None
        timings: dict[str, float] = {}
        total_started = phase_started = timing_now()
        workspace_state = bind_request_render_workspace(
            adapter=self._workspace_binding_adapter,
            run=run,
            draft=draft,
            session_key=session_key,
            agent_id=agent_id,
            persist=persist,
        )
        phase_started = record_timing(timings, "ensure_workspace", phase_started)
        render_metadata = self._tool_schema_mirror_adapter.resolve_render_metadata(
            session_key=session_key,
            run_id=run.id,
            draft=draft,
            allow_tree_fallback=persist,
        )
        requested_tool_schema_names = resolve_requested_tool_schema_names(
            adapter=self._tool_schema_mirror_adapter,
            draft=draft,
            render_metadata=render_metadata,
            session_key=session_key,
        )
        phase_started = record_timing(
            timings,
            "resolve_tool_schema_metadata",
            phase_started,
        )
        input_selection = build_request_render_input_selection(draft, run_id=run.id)
        provider_profile = draft.llm_api_family or draft.llm_id
        control_slice = build_request_control_slice(
            builder=self._control_slice_builder,
            session_key=session_key,
            run_id=run.id,
            provider_profile=provider_profile,
            read_only=workspace_state.read_only,
            requested_tool_schema_names=requested_tool_schema_names,
            input_selection=input_selection,
        )
        phase_started = record_timing(timings, "build_control_slice", phase_started)
        if persist and self._slice_builder is None:
            raise RuntimeError(
                "Context Slice builder is required for persisted request render snapshots."
            )
        if persist:
            self._tool_schema_mirror_adapter.sync_requested_tool_schema_nodes(
                session_key=session_key,
                run_id=run.id,
                schema_names=(
                    *requested_tool_schema_names,
                    *metadata_string_values(
                        render_metadata.get("default_tool_schema_ids"),
                    ),
                ),
                render_metadata=render_metadata,
            )
            phase_started = record_timing(
                timings,
                "sync_requested_tool_schema_nodes",
                phase_started,
            )
        provider_attachments: dict[str, object] = {}
        artifact_content_blocks: tuple[dict[str, object], ...] = ()
        context_slice = build_request_context_slice(
            builder=self._slice_builder,
            session_key=session_key,
            run_id=run.id,
            provider_profile=provider_profile,
            read_only=workspace_state.read_only,
            requested_tool_schema_names=requested_tool_schema_names,
            input_selection=input_selection,
        )
        phase_started = record_timing(timings, "build_context_slice", phase_started)
        if persist and context_slice is None:
            raise RuntimeError(
                "Context Slice builder is required for persisted request render snapshots."
            )
        slice_projection = project_request_render_slices(
            draft=draft,
            control_slice=control_slice,
            context_slice=context_slice,
        )
        visible_tool_selection = visible_tool_schema_selection(
            adapter=self._tool_schema_mirror_adapter,
            context_slice=context_slice,
            available_schemas=draft.tool_schemas,
            requested_schema_names=requested_tool_schema_names,
        )
        visible_tool_schemas = visible_tool_selection.schemas
        visible_tool_schema_refs = visible_tool_selection.refs
        phase_started = record_timing(
            timings,
            "resolve_visible_tool_schemas",
            phase_started,
        )
        estimate = (
            ContextEstimate.from_payload(context_slice.report.budget)
            if context_slice is not None
            else ContextEstimate()
        )
        estimate_payload = estimate.to_payload()
        metadata_bundle = build_request_render_metadata_bundle(
            builder=self._request_render_snapshot_metadata_builder,
            draft=draft,
            flow_context=workspace_state.flow_context,
            tree_revision=workspace_state.workspace.active_revision,
            control_slice=control_slice,
            context_slice=context_slice,
            slice_projection=slice_projection,
            input_selection=input_selection,
            visible_tool_schemas=visible_tool_schemas,
            render_metadata=render_metadata,
        )
        snapshot_metadata = metadata_bundle.metadata
        request_render_report = metadata_bundle.render_report
        phase_started = record_timing(timings, "build_snapshot_metadata", phase_started)
        request_render_snapshot_id = f"ctxpreview_{run.id}"
        pre_request_render_snapshot_timings = dict(timings)
        pre_request_render_snapshot_timings["total_before_request_render_snapshot_ms"] = (
            elapsed_ms(total_started)
        )
        attach_request_render_timings(
            snapshot_metadata,
            request_render_report,
            pre_request_render_snapshot_timings,
        )
        if persist:
            snapshot = record_request_render_context_snapshot(
                render_service=self._render_service,
                session_key=session_key,
                run_id=run.id,
                estimate=estimate,
                slice_projection=slice_projection,
                input_selection=input_selection,
                provider_attachments=provider_attachments,
                metadata=snapshot_metadata,
            )
            phase_started = record_timing(
                timings,
                "record_context_snapshot",
                phase_started,
            )
            request_render_snapshot_id = snapshot.id
        if persist and self._request_render_snapshot_recorder.available:
            pre_request_render_snapshot_timings = dict(timings)
            pre_request_render_snapshot_timings["total_before_request_render_snapshot_ms"] = (
                elapsed_ms(total_started)
            )
            attach_request_render_timings(
                snapshot_metadata,
                request_render_report,
                pre_request_render_snapshot_timings,
            )
            request_render_snapshot_id = record_request_render_snapshot_if_available(
                recorder=self._request_render_snapshot_recorder,
                context_snapshot_id=snapshot.id,
                workspace_id=workspace_state.workspace.id,
                session_key=session_key,
                run_id=run.id,
                tree_revision=workspace_state.workspace.active_revision,
                model=draft.llm_id,
                slice_projection=slice_projection,
                visible_tool_schema_refs=visible_tool_schema_refs,
                estimate=estimate,
                request_render_report=request_render_report,
                timings=pre_request_render_snapshot_timings,
                metadata=snapshot_metadata,
            )
            record_timing(timings, "record_request_render_snapshot", phase_started)
        timings["total_ms"] = elapsed_ms(total_started)
        return build_request_render_snapshot_record(
            snapshot_id=request_render_snapshot_id,
            estimate_payload=estimate_payload,
            slice_projection=slice_projection,
            input_selection=input_selection,
            metadata=snapshot_metadata,
            visible_tool_schemas=visible_tool_schemas,
            visible_tool_schema_refs=visible_tool_schema_refs,
            artifact_content_blocks=artifact_content_blocks,
        )
