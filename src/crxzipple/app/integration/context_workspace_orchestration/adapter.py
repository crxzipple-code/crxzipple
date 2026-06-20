"""Orchestration to Context Workspace integration."""

from __future__ import annotations

from time import perf_counter

from crxzipple.modules.context_workspace.application import (
    BuildContextControlSliceInput,
    BuildContextObservationSliceInput,
    ContextActionInput,
    ContextObservationSnapshotService,
    ContextTreeService,
    ContextWorkspaceService,
    EnsureContextWorkspaceInput,
    RecordRequestRenderSnapshotInput,
    RecordContextSnapshotInput,
    RequestRenderSnapshotService,
)
from crxzipple.modules.context_workspace.application.ports import (
    ContextControlSliceBuilder,
    ContextSliceBuilder,
)
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextEstimate,
    ContextSnapshot,
    ContextSnapshotNotFoundError,
    ContextWorkspace,
    ContextWorkspaceNotFoundError,
)
from crxzipple.modules.llm.domain import LlmCapability, ToolSchema
from crxzipple.modules.orchestration.application.flow_context import (
    build_flow_context_payload,
)
from crxzipple.modules.orchestration.application.ports import (
    RequestRenderSnapshotRecord,
)
from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
    RuntimeLlmRequestDraft,
)
from crxzipple.modules.orchestration.domain import OrchestrationRun

from .artifact_mirror import build_artifact_content_blocks
from .run_workspace_metadata import build_run_workspace_metadata
from .snapshot_metadata import (
    build_context_snapshot_metadata,
    _draft_input_session_item_refs,
    _draft_transcript_budget,
    _merged_protocol_required_refs,
    _metadata_dict_list,
)
from .tool_schema_bootstrap import (
    merge_default_tool_schema_metadata,
    resolve_draft_tool_schema_metadata,
    resolve_default_tool_schema_metadata,
    ToolRuntimeRequestCatalog,
)


class ContextWorkspaceRunSnapshotAdapter:
    """Records a tree-backed context snapshot for real orchestration runs.

    The adapter is intentionally side-effect narrow: it materializes Context
    Workspace state alongside the existing RuntimeLlmRequestDraftCollector output and returns
    a RequestRenderSnapshotRecord for runtime request construction.
    """

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
        self._workspace_service = workspace_service
        self._render_service = render_service
        self._tree_service = tree_service
        self._slice_builder = slice_builder
        self._control_slice_builder = control_slice_builder
        self._request_render_snapshot_service = request_render_snapshot_service
        self._runtime_request_catalog = runtime_request_catalog
        self._artifact_service = artifact_service

    def preview_run_request_render_snapshot(
        self,
        *,
        run: OrchestrationRun,
        draft: RuntimeLlmRequestDraft,
    ) -> RequestRenderSnapshotRecord | None:
        return self._record_lightweight_request_snapshot(
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
        if self._request_render_snapshot_service is None:
            return None
        try:
            self._request_render_snapshot_service.get_snapshot(snapshot.id)
        except ContextSnapshotNotFoundError:
            return None
        return self._record_from_snapshot(snapshot, draft=draft)

    def record_run_request_render_snapshot(
        self,
        *,
        run: OrchestrationRun,
        draft: RuntimeLlmRequestDraft,
    ) -> RequestRenderSnapshotRecord | None:
        return self._record_lightweight_request_snapshot(
            run=run,
            draft=draft,
        )

    def _record_lightweight_request_snapshot(
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
        total_started = phase_started = perf_counter()
        flow_context = build_flow_context_payload(
            mode=draft.mode,
            hint_payload=draft.flow_hint,
        )
        run_workspace_metadata = build_run_workspace_metadata(
            run=run,
            draft=draft,
            flow_context=flow_context.to_payload(),
        )
        workspace = self._workspace_for_request_snapshot(
            session_key=session_key,
            agent_id=agent_id,
            metadata=run_workspace_metadata,
            persist=persist,
        )
        phase_started = _record_timing(timings, "ensure_workspace", phase_started)
        render_metadata = merge_default_tool_schema_metadata(
            resolve_draft_tool_schema_metadata(draft),
            resolve_default_tool_schema_metadata(
                tree_service=self._tree_service,
                runtime_request_catalog=self._runtime_request_catalog,
                session_key=session_key,
                run_id=run.id,
                draft=draft,
                allow_tree_fallback=persist,
            ),
        )
        requested_tool_schema_names = tuple(
            schema.name
            for schema in _request_render_tool_schemas(
                draft.tool_schemas,
                render_metadata=render_metadata,
                tree_service=self._tree_service,
                session_key=session_key,
                surface_contract=draft.surface_policy.surface_contract,
                active_tool_names=(),
            )
        )
        phase_started = _record_timing(
            timings,
            "resolve_tool_schema_metadata",
            phase_started,
        )
        control_slice = (
            self._control_slice_builder.build_control_slice(
                data=BuildContextControlSliceInput(
                    session_key=session_key,
                    run_id=run.id,
                    audience="llm_request",
                    provider_profile=draft.llm_api_family or draft.llm_id,
                    metadata={
                        "read_only": not persist,
                        "requested_tool_schema_names": list(
                            requested_tool_schema_names,
                        ),
                        "protocol_required_refs": [
                            dict(ref)
                            for ref in _merged_protocol_required_refs(
                                _draft_input_session_item_refs(draft),
                                _draft_transcript_budget(draft),
                            )
                        ],
                    },
                ),
            )
            if self._control_slice_builder is not None
            else None
        )
        phase_started = _record_timing(timings, "build_control_slice", phase_started)
        if persist and self._slice_builder is None:
            raise RuntimeError(
                "Context Slice builder is required for persisted request render snapshots."
            )
        if persist:
            _sync_requested_tool_schema_nodes(
                tree_service=self._tree_service,
                session_key=session_key,
                run_id=run.id,
                schema_names=(
                    *requested_tool_schema_names,
                    *_metadata_string_values(
                        render_metadata.get("default_tool_schema_ids"),
                    ),
                ),
                render_metadata=render_metadata,
            )
        provider_attachments: dict[str, object] = {}
        artifact_content_blocks: tuple[dict[str, object], ...] = ()
        draft_input_session_item_refs = _draft_input_session_item_refs(draft)
        draft_input_budget = _draft_transcript_budget(draft)
        protocol_required_refs = tuple(
            _merged_protocol_required_refs(
                draft_input_session_item_refs,
                draft_input_budget,
            ),
        )
        session_item_max_chars = _request_session_item_max_chars(draft)
        context_slice = (
            self._slice_builder.build_slice(
                data=BuildContextObservationSliceInput(
                    session_key=session_key,
                    run_id=run.id,
                    audience="llm_request",
                    provider_profile=draft.llm_api_family or draft.llm_id,
                    metadata={
                        "read_only": not persist,
                        "requested_tool_schema_names": list(
                            requested_tool_schema_names,
                        ),
                        "protocol_required_refs": [
                            dict(ref) for ref in protocol_required_refs
                        ],
                        **(
                            {"session_item_max_chars": session_item_max_chars}
                            if session_item_max_chars is not None
                            else {}
                        ),
                    },
                ),
            )
            if self._slice_builder is not None
            else None
        )
        phase_started = _record_timing(timings, "build_context_slice", phase_started)
        if persist and context_slice is None:
            raise RuntimeError(
                "Context Slice builder is required for persisted request render snapshots."
            )
        control_selected_node_ids = _control_slice_selected_node_ids(control_slice)
        context_slice_refs = _context_slice_session_refs(context_slice)
        context_slice_node_ids = _context_slice_included_node_ids(context_slice)
        context_slice_omitted_node_ids = _context_slice_omitted_node_ids(context_slice)
        context_slice_report_refs = _context_slice_report_refs(context_slice)
        context_slice_loss = _context_slice_loss(context_slice)
        projected_input_items = _context_slice_projected_input_items(context_slice)
        included_refs = context_slice_refs if context_slice is not None else ()
        included_node_ids = context_slice_node_ids if context_slice is not None else ()
        execution_required_refs = _snapshot_ref_tuple(
            draft_input_budget.get("execution_chain_protocol_required_refs"),
        )
        collapsed_refs = _context_slice_collapsed_refs(context_slice)
        if context_slice is not None:
            context_slice_tool_schemas = _context_slice_tool_schemas(
                context_slice,
                available_schemas=draft.tool_schemas,
            )
            visible_tool_schemas = context_slice_tool_schemas
            visible_tool_schema_refs = _context_slice_tool_schema_refs(
                context_slice,
                schemas=context_slice_tool_schemas,
            )
        else:
            visible_tool_schemas = ()
            visible_tool_schema_refs = ()
        phase_started = _record_timing(
            timings,
            "resolve_visible_tool_schemas",
            phase_started,
        )
        visible_input_summary = _visible_input_summary(
            included_refs=included_refs,
            protocol_required_refs=protocol_required_refs,
            collapsed_refs=collapsed_refs,
            visible_tool_schemas=visible_tool_schemas,
            control_slice=control_slice,
            context_slice=context_slice,
        )
        estimate = (
            ContextEstimate.from_payload(context_slice.report.budget)
            if context_slice is not None
            else ContextEstimate()
        )
        estimate_payload = estimate.to_payload()
        snapshot_metadata: dict[str, object] = {
            "snapshot_kind": "request_render",
            "tree_schema_version": "request-render-snapshot",
            "history_delivery": "provider_native_request",
            "request_context_source": (
                "context_slice"
                if context_slice is not None
                else "missing_context_slice"
            ),
            "active_session_id": draft.active_session_id,
            "mode": draft.mode.value,
            "flow_context": flow_context.to_payload(),
            "workspace_dir": draft.workspace_dir,
            "tree_revision": workspace.active_revision,
            "control_slice_id": (
                control_slice.slice_id if control_slice is not None else None
            ),
            "control_slice_selected_ref_count": (
                len(control_slice.selected_refs)
                if control_slice is not None
                else 0
            ),
            "control_slice_selected_node_count": len(control_selected_node_ids),
            "control_slice_active_tool_count": (
                len(control_slice.active_tools)
                if control_slice is not None
                else 0
            ),
            "context_slice_id": (
                context_slice.slice_id if context_slice is not None else None
            ),
            "context_slice_item_count": (
                len(context_slice.items) if context_slice is not None else 0
            ),
            "context_slice_included_node_count": len(context_slice_node_ids),
            "context_slice_omitted_node_count": len(context_slice_omitted_node_ids),
            "context_slice_active_tool_count": (
                len(context_slice.active_tools)
                if context_slice is not None
                else 0
            ),
            "context_slice_projected_input_item_count": len(projected_input_items),
            "context_slice_archived_ref_count": len(
                context_slice_report_refs["archived_refs"],
            ),
            "context_slice_redacted_ref_count": len(
                context_slice_report_refs["redacted_refs"],
            ),
            "context_slice_unresolved_ref_count": len(
                context_slice_report_refs["unresolved_refs"],
            ),
            "context_slice_loss": context_slice_loss,
            "draft_input_message_count": len(draft.messages),
            "draft_input_roles": [
                message.role.value for message in draft.messages
            ],
            "draft_input_session_item_count": len(included_refs),
            "draft_input_session_item_frontier": dict(
                draft_input_budget.get("frontier")
                if isinstance(draft_input_budget.get("frontier"), dict)
                else {},
            ),
            "draft_input_budget_summary": _transcript_budget_summary(
                draft_input_budget,
            ),
            "protocol_required_ref_count": len(protocol_required_refs),
            "execution_chain_protocol_required_ref_count": len(
                execution_required_refs,
            ),
            "collapsed_ref_count": len(collapsed_refs),
            "mirrored_tool_schema_count": len(visible_tool_schemas),
            "provider_tool_schema_names": [
                schema.name for schema in visible_tool_schemas
            ],
            "visible_input_summary": visible_input_summary,
            "tool_schema_mirror_budget": {
                "status": "ok",
                "default_schema_source": render_metadata.get(
                    "default_tool_schema_source",
                ),
                "default_requested_count": len(
                    render_metadata.get("default_tool_schema_ids", ())
                    if isinstance(
                        render_metadata.get("default_tool_schema_ids"),
                        list | tuple,
                    )
                    else (),
                ),
                "default_mirrored_count": len(visible_tool_schemas),
                "available_count": len(draft.tool_schemas),
                "enabled_candidate_count": len(visible_tool_schemas),
                "group_count": len(
                    render_metadata.get("default_tool_schema_group_refs", ())
                    if isinstance(
                        render_metadata.get("default_tool_schema_group_refs"),
                        list | tuple,
                    )
                    else (),
                ),
            },
            "tool_schema_mirror_default_schema_source": render_metadata.get(
                "default_tool_schema_source",
            ),
            "runtime_request_report": (
                draft.report.to_payload()
                if draft.report is not None
                else None
            ),
            "runtime_request_snapshot": {
                "llm_id": draft.llm_id,
                "llm_api_family": draft.llm_api_family,
                "llm_capabilities": [
                    capability.value for capability in draft.llm_capabilities
                ],
                "input_item_count": len(draft.input_items),
                "message_count": len(draft.messages),
                "tool_schema_count": len(visible_tool_schemas),
                "available_tool_schema_count": len(draft.tool_schemas),
                "tree_revision": workspace.active_revision,
            },
            "request_render_snapshot": {
                "kind": "request_render",
                "debug_body_included": False,
                "full_tree_rendered": False,
                "owner_children_refreshed": False,
                "visible_input_summary": visible_input_summary,
            },
        }
        phase_started = _record_timing(timings, "build_snapshot_metadata", phase_started)
        request_render_snapshot_id = f"ctxpreview_{run.id}"
        pre_request_render_snapshot_timings = dict(timings)
        pre_request_render_snapshot_timings["total_before_request_render_snapshot_ms"] = (
            _elapsed_ms(total_started)
        )
        snapshot_metadata["request_render_timings"] = dict(
            pre_request_render_snapshot_timings,
        )
        request_render_metadata = snapshot_metadata.get("request_render_snapshot")
        if isinstance(request_render_metadata, dict):
            request_render_metadata["timings"] = dict(
                pre_request_render_snapshot_timings,
            )
        if persist:
            snapshot = self._render_service.record_snapshot(
                RecordContextSnapshotInput(
                    session_key=session_key,
                    run_id=run.id,
                    debug_body="",
                    provider_attachments=provider_attachments,
                    estimate=estimate,
                    included_node_ids=included_node_ids,
                    mirrored_node_ids=(),
                    included_refs=included_refs,
                    collapsed_refs=collapsed_refs,
                    protocol_required_refs=protocol_required_refs,
                    metadata=snapshot_metadata,
                    include_metadata_defaults=False,
                ),
            )
            phase_started = _record_timing(
                timings,
                "record_context_snapshot",
                phase_started,
            )
            request_render_snapshot_id = snapshot.id
        if persist and self._request_render_snapshot_service is not None:
            pre_request_render_snapshot_timings = dict(timings)
            pre_request_render_snapshot_timings["total_before_request_render_snapshot_ms"] = (
                _elapsed_ms(total_started)
            )
            snapshot_metadata["request_render_timings"] = dict(
                pre_request_render_snapshot_timings,
            )
            request_render_metadata = snapshot_metadata.get("request_render_snapshot")
            if isinstance(request_render_metadata, dict):
                request_render_metadata["timings"] = dict(
                    pre_request_render_snapshot_timings,
                )
            request_render_snapshot = self._request_render_snapshot_service.record_snapshot(
                RecordRequestRenderSnapshotInput(
                    snapshot_id=snapshot.id,
                    workspace_id=workspace.id,
                    session_key=session_key,
                    run_id=run.id,
                    tree_revision=workspace.active_revision,
                    turn_id=run.id,
                    model=draft.llm_id,
                    renderer_id="context_workspace.request_render_snapshot",
                    renderer_version="2026-06-18",
                    input_item_refs=included_refs,
                    projected_input_items=projected_input_items,
                    tool_schema_refs=visible_tool_schema_refs,
                    resource_refs=collapsed_refs,
                    estimated_tokens=estimate.text_tokens,
                    render_report={
                        "kind": "request_render",
                        "debug_body_included": False,
                        "full_tree_rendered": False,
                        "owner_children_refreshed": False,
                        "tool_schema_count": len(visible_tool_schemas),
                        "available_tool_schema_count": len(draft.tool_schemas),
                        "control_slice_id": (
                            control_slice.slice_id
                            if control_slice is not None
                            else None
                        ),
                        "control_slice_selected_ref_count": (
                            len(control_slice.selected_refs)
                            if control_slice is not None
                            else 0
                        ),
                        "control_slice_selected_node_count": len(
                            control_selected_node_ids,
                        ),
                        "context_slice_id": (
                            context_slice.slice_id
                            if context_slice is not None
                            else None
                        ),
                        "context_slice_item_count": (
                            len(context_slice.items)
                            if context_slice is not None
                            else 0
                        ),
                        "context_slice_omitted_node_count": len(
                            context_slice_omitted_node_ids,
                        ),
                        "context_slice_archived_ref_count": len(
                            context_slice_report_refs["archived_refs"],
                        ),
                        "context_slice_redacted_ref_count": len(
                            context_slice_report_refs["redacted_refs"],
                        ),
                        "context_slice_unresolved_ref_count": len(
                            context_slice_report_refs["unresolved_refs"],
                        ),
                        "context_slice_loss": context_slice_loss,
                        "included_node_count": len(included_node_ids),
                        "input_item_ref_count": len(included_refs),
                        "protocol_required_ref_count": len(protocol_required_refs),
                        "visible_input_summary": visible_input_summary,
                        "timings": dict(pre_request_render_snapshot_timings),
                    },
                    timings=pre_request_render_snapshot_timings,
                    metadata=snapshot_metadata,
                ),
            )
            request_render_snapshot_id = request_render_snapshot.id
            phase_started = _record_timing(
                timings,
                "record_request_render_snapshot",
                phase_started,
            )
        timings["total_ms"] = _elapsed_ms(total_started)
        return RequestRenderSnapshotRecord(
            snapshot_id=request_render_snapshot_id,
            estimate=estimate_payload,
            included_node_ids=included_node_ids,
            mirrored_node_ids=(),
            included_refs=included_refs,
            collapsed_refs=collapsed_refs,
            protocol_required_refs=protocol_required_refs,
            input_item_refs=included_refs,
            projected_input_items=projected_input_items,
            metadata=snapshot_metadata,
            tool_schemas=visible_tool_schemas,
            tool_schema_refs=visible_tool_schema_refs,
            tool_schema_mirror_available=bool(visible_tool_schemas),
            artifact_content_blocks=artifact_content_blocks,
            parent_snapshot_id=None,
            parent_tree_revision=None,
        )

    def _record_from_snapshot(
        self,
        snapshot: ContextSnapshot,
        *,
        draft: RuntimeLlmRequestDraft,
    ) -> RequestRenderSnapshotRecord:
        provider_attachments = dict(snapshot.provider_attachments)
        metadata = dict(snapshot.metadata)
        tool_schemas = self._tool_schemas_from_recorded_request_render_snapshot(
            snapshot,
        )
        return RequestRenderSnapshotRecord(
            snapshot_id=snapshot.id,
            estimate=snapshot.estimate.to_payload(),
            included_node_ids=snapshot.included_node_ids,
            mirrored_node_ids=snapshot.mirrored_node_ids,
            included_refs=snapshot.included_refs,
            collapsed_refs=snapshot.collapsed_refs,
            protocol_required_refs=snapshot.protocol_required_refs,
            input_item_refs=(
                self._input_item_refs_from_recorded_request_render_snapshot(snapshot)
            ),
            projected_input_items=(
                self._projected_input_items_from_recorded_request_render_snapshot(
                    snapshot,
                )
            ),
            metadata=metadata,
            tool_schemas=tool_schemas,
            tool_schema_refs=self._tool_schema_refs_from_recorded_request_render_snapshot(
                snapshot,
            ),
            tool_schema_mirror_available=bool(tool_schemas),
            artifact_content_blocks=build_artifact_content_blocks(
                provider_attachments,
                artifact_service=self._artifact_service,
                allow_vision=LlmCapability.VISION_INPUT in draft.llm_capabilities,
            ),
            parent_snapshot_id=snapshot.parent_snapshot_id,
            parent_tree_revision=snapshot.parent_tree_revision,
        )

    def _input_item_refs_from_recorded_request_render_snapshot(
        self,
        snapshot: ContextSnapshot,
    ) -> tuple[dict[str, object], ...]:
        if snapshot.metadata.get("snapshot_kind") != "request_render":
            return ()
        if self._request_render_snapshot_service is None:
            return ()
        try:
            request_render_snapshot = self._request_render_snapshot_service.get_snapshot(
                snapshot.id,
            )
        except ContextSnapshotNotFoundError:
            return ()
        return tuple(dict(item) for item in request_render_snapshot.input_item_refs)

    def _projected_input_items_from_recorded_request_render_snapshot(
        self,
        snapshot: ContextSnapshot,
    ) -> tuple[dict[str, object], ...]:
        if snapshot.metadata.get("snapshot_kind") != "request_render":
            return ()
        if self._request_render_snapshot_service is None:
            return ()
        try:
            request_render_snapshot = self._request_render_snapshot_service.get_snapshot(
                snapshot.id,
            )
        except ContextSnapshotNotFoundError:
            return ()
        return tuple(dict(item) for item in request_render_snapshot.projected_input_items)

    def _tool_schemas_from_recorded_request_render_snapshot(
        self,
        snapshot: ContextSnapshot,
    ) -> tuple[ToolSchema, ...] | None:
        if snapshot.metadata.get("snapshot_kind") != "request_render":
            return ()
        if self._request_render_snapshot_service is None:
            return ()
        try:
            request_render_snapshot = self._request_render_snapshot_service.get_snapshot(
                snapshot.id,
            )
        except ContextSnapshotNotFoundError:
            return ()
        schemas: list[ToolSchema] = []
        seen: set[str] = set()
        for ref in request_render_snapshot.tool_schema_refs:
            raw_schema = ref.get("schema")
            schema = (
                ToolSchema.from_payload(dict(raw_schema))
                if isinstance(raw_schema, dict)
                else None
            )
            if schema is None:
                raw_name = ref.get("name")
                if not isinstance(raw_name, str) or not raw_name.strip():
                    continue
                schema = ToolSchema(name=raw_name.strip())
            if schema.name in seen:
                continue
            schemas.append(schema)
            seen.add(schema.name)
        return tuple(schemas)

    def _tool_schema_refs_from_recorded_request_render_snapshot(
        self,
        snapshot: ContextSnapshot,
    ) -> tuple[dict[str, object], ...]:
        if snapshot.metadata.get("snapshot_kind") != "request_render":
            return ()
        if self._request_render_snapshot_service is None:
            return ()
        try:
            request_render_snapshot = self._request_render_snapshot_service.get_snapshot(
                snapshot.id,
            )
        except ContextSnapshotNotFoundError:
            return ()
        return tuple(dict(ref) for ref in request_render_snapshot.tool_schema_refs)

    def _workspace_for_request_snapshot(
        self,
        *,
        session_key: str,
        agent_id: str,
        metadata: dict[str, object],
        persist: bool,
    ) -> ContextWorkspace:
        if persist:
            return self._workspace_service.ensure_workspace(
                EnsureContextWorkspaceInput(
                    session_key=session_key,
                    agent_id=agent_id,
                    metadata=metadata,
                    refresh_expanded_children=False,
                ),
            )
        try:
            return self._workspace_service.get_by_session(session_key)
        except ContextWorkspaceNotFoundError:
            return self._workspace_service.ensure_workspace(
                EnsureContextWorkspaceInput(
                    session_key=session_key,
                    agent_id=agent_id,
                    metadata=metadata,
                    refresh_expanded_children=False,
                ),
            )


def _snapshot_ref_tuple(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(dict(ref) for ref in value if isinstance(ref, dict))


def _record_timing(
    timings: dict[str, float],
    phase: str,
    started: float,
) -> float:
    now = perf_counter()
    timings[f"{phase}_ms"] = round((now - started) * 1000, 3)
    return now


def _elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000, 3)


def _snapshot_budget_dict(metadata: dict[str, object]) -> dict[str, object]:
    value = metadata.get("draft_input_budget")
    if not isinstance(value, dict):
        return {}
    return dict(value)


def _transcript_budget_summary(budget: dict[str, object]) -> dict[str, object]:
    summary: dict[str, object] = {}
    for key in (
        "source",
        "truncated",
        "protocol_required_preserved",
        "selected_item_count",
        "available_item_count",
        "collapsed_count",
    ):
        value = budget.get(key)
        if value is not None:
            summary[key] = value
    frontier = budget.get("frontier")
    if isinstance(frontier, dict):
        summary["frontier"] = dict(frontier)
    tool_result_stats = budget.get("tool_result_stats")
    if isinstance(tool_result_stats, dict):
        summary["tool_result_stats"] = dict(tool_result_stats)
    return summary


def _visible_input_summary(
    *,
    included_refs: tuple[dict[str, object], ...],
    protocol_required_refs: tuple[dict[str, object], ...],
    collapsed_refs: tuple[dict[str, object], ...],
    visible_tool_schemas: tuple[ToolSchema, ...],
    control_slice: object | None,
    context_slice: object | None = None,
) -> dict[str, object]:
    summary: dict[str, object] = {
        "debug_body_included": False,
        "full_tree_rendered": False,
        "owner_children_refreshed": False,
        "input_item_ref_count": len(included_refs),
        "protocol_required_ref_count": len(protocol_required_refs),
        "collapsed_ref_count": len(collapsed_refs),
        "tool_schema_count": len(visible_tool_schemas),
        "tool_schema_names": [schema.name for schema in visible_tool_schemas],
        "input_ref_owner_counts": _ref_counts(included_refs, "owner_module"),
        "input_ref_kind_counts": _ref_counts(included_refs, "owner_kind"),
    }
    if control_slice is not None:
        summary["control_slice_id"] = getattr(control_slice, "slice_id", None)
        summary["included_node_count"] = len(
            _control_slice_selected_node_ids(control_slice),
        )
        summary["control_slice_selected_ref_count"] = len(
            getattr(control_slice, "selected_refs", ()) or (),
        )
        summary["control_slice_active_tool_count"] = len(
            getattr(control_slice, "active_tools", ()) or (),
        )
    if context_slice is not None:
        summary["context_slice_id"] = getattr(context_slice, "slice_id", None)
        summary["context_slice_item_count"] = len(
            getattr(context_slice, "items", ()) or (),
        )
        summary["context_slice_active_tool_count"] = len(
            getattr(context_slice, "active_tools", ()) or (),
        )
    return {
        key: value
        for key, value in summary.items()
        if value not in (None, "", {}, [])
    }


def _control_slice_selected_node_ids(control_slice: object | None) -> tuple[str, ...]:
    if control_slice is None:
        return ()
    report = getattr(control_slice, "report", None)
    selected_node_ids = getattr(report, "selected_node_ids", ()) if report else ()
    if isinstance(selected_node_ids, (list, tuple)):
        return tuple(
            str(node_id)
            for node_id in selected_node_ids
            if str(node_id).strip()
        )
    return tuple(
        str(node_id)
        for ref in (getattr(control_slice, "selected_refs", ()) or ())
        for node_id in (getattr(ref, "node_id", ""),)
        if str(node_id).strip()
    )


def _context_slice_included_node_ids(context_slice: object | None) -> tuple[str, ...]:
    if context_slice is None:
        return ()
    report = getattr(context_slice, "report", None)
    included_node_ids = getattr(report, "included_node_ids", ()) if report else ()
    if not isinstance(included_node_ids, (list, tuple)):
        return ()
    return tuple(
        str(node_id)
        for node_id in included_node_ids
        if str(node_id).strip()
    )


def _context_slice_omitted_node_ids(context_slice: object | None) -> tuple[str, ...]:
    if context_slice is None:
        return ()
    report = getattr(context_slice, "report", None)
    omitted_node_ids = getattr(report, "omitted_node_ids", ()) if report else ()
    if not isinstance(omitted_node_ids, (list, tuple)):
        return ()
    return tuple(
        str(node_id)
        for node_id in omitted_node_ids
        if str(node_id).strip()
    )


def _context_slice_session_refs(context_slice: object | None) -> tuple[dict[str, object], ...]:
    if context_slice is None:
        return ()
    refs: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in getattr(context_slice, "items", ()) or ():
        if getattr(item, "owner", None) != "session":
            continue
        owner_ref = getattr(item, "owner_ref", None)
        if not isinstance(owner_ref, dict):
            continue
        item_id = _metadata_text_value(
            owner_ref.get("session_item_id"),
            owner_ref.get("item_id"),
            owner_ref.get("owner_id"),
        )
        if item_id is None or item_id in seen:
            continue
        ref = dict(owner_ref)
        ref.setdefault("item_id", item_id)
        ref.setdefault("session_item_id", item_id)
        ref.setdefault("node_id", getattr(item, "node_id", None) or getattr(item, "item_id", ""))
        ref.setdefault("owner_module", "session")
        ref.setdefault("owner_kind", getattr(item, "kind", "session_item"))
        ref.setdefault("owner_id", item_id)
        refs.append(ref)
        seen.add(item_id)
    return tuple(refs)


def _context_slice_projected_input_items(
    context_slice: object | None,
) -> tuple[dict[str, object], ...]:
    if context_slice is None:
        return ()
    projected: list[dict[str, object]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for item in getattr(context_slice, "items", ()) or ():
        if getattr(item, "owner", None) != "session":
            continue
        owner_ref = getattr(item, "owner_ref", None)
        if not isinstance(owner_ref, dict):
            continue
        node_id = _metadata_text_value(
            getattr(item, "node_id", None),
            getattr(item, "item_id", None),
        )
        session_item_id = _metadata_text_value(
            owner_ref.get("session_item_id"),
            owner_ref.get("item_id"),
            owner_ref.get("owner_id"),
        )
        if session_item_id is None:
            continue
        payload = _context_slice_item_input_payload(item, owner_ref)
        if payload is None:
            continue
        payload_body = payload["payload"]
        protocol_id = ""
        if isinstance(payload_body, dict):
            protocol_id = _metadata_text_value(
                payload_body.get("call_id"),
                payload_body.get("name"),
            ) or ""
        dedupe_key = (session_item_id, str(payload["kind"]), protocol_id)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        metadata = {
            "owner": "session",
            "kind": getattr(item, "kind", "session_item"),
            "session_item_id": session_item_id,
            "node_id": node_id,
        }
        for key in (
            "sequence_no",
            "tool_call_id",
            "tool_name",
            "tool_run_id",
            "llm_response_item_id",
        ):
            value = owner_ref.get(key)
            if value not in (None, "", {}, []):
                metadata[key] = value
        projected.append(
            {
                "kind": payload["kind"],
                "payload": payload["payload"],
                "source": "context_slice",
                "metadata": {
                    key: value
                    for key, value in metadata.items()
                    if value not in (None, "", {}, [])
                },
            },
        )
    return _drop_unpaired_projected_function_items(tuple(projected))


def _drop_unpaired_projected_function_items(
    items: tuple[dict[str, object], ...],
) -> tuple[dict[str, object], ...]:
    call_ids = {
        call_id
        for item in items
        for payload in (item.get("payload"),)
        if item.get("kind") == "function_call"
        and isinstance(payload, dict)
        for call_id in (_metadata_text_value(payload.get("call_id")),)
        if call_id is not None
    }
    output_ids = {
        call_id
        for item in items
        for payload in (item.get("payload"),)
        if item.get("kind") == "function_call_output"
        and isinstance(payload, dict)
        for call_id in (_metadata_text_value(payload.get("call_id")),)
        if call_id is not None
    }
    if not call_ids and not output_ids:
        return items
    paired_ids = call_ids & output_ids
    filtered: list[dict[str, object]] = []
    for item in items:
        kind = item.get("kind")
        if kind not in {"function_call", "function_call_output"}:
            filtered.append(item)
            continue
        payload = item.get("payload")
        call_id = (
            _metadata_text_value(payload.get("call_id"))
            if isinstance(payload, dict)
            else None
        )
        if call_id is not None and call_id in paired_ids:
            filtered.append(item)
    return tuple(filtered)


def _context_slice_item_input_payload(
    item: object,
    owner_ref: dict[str, object],
) -> dict[str, object] | None:
    kind = str(getattr(item, "kind", "") or "").strip()
    session_item_kind = _metadata_text_value(owner_ref.get("kind"))
    source_kind = _metadata_text_value(owner_ref.get("source_kind"))
    provider_item_type = _metadata_text_value(owner_ref.get("provider_item_type"))
    runtime_semantic_kind = _metadata_text_value(owner_ref.get("runtime_semantic_kind"))
    if owner_ref.get("model_visible") is False:
        return None
    if kind in {"reasoning", "agent_progress"}:
        return None
    if session_item_kind in {
        "reasoning",
        "agent_progress",
        "provider_external_activity",
        "runtime_notice",
        "runtime_error",
        "unknown",
    }:
        return None
    if runtime_semantic_kind in {"runtime.reasoning", "runtime.assistant_progress"}:
        return None
    if provider_item_type == "reasoning":
        return None
    if source_kind == "approval_request":
        return None
    tool_call_id = _metadata_text_value(
        owner_ref.get("tool_call_id"),
        owner_ref.get("call_id"),
    )
    tool_name = _metadata_text_value(
        owner_ref.get("tool_name"),
        owner_ref.get("name"),
    )
    arguments = owner_ref.get("arguments")
    role = (
        _metadata_text_value(owner_ref.get("role"))
        or _role_from_context_slice_item(item)
        or "user"
    )
    content = getattr(item, "content", None)
    text = _metadata_text_value(getattr(item, "text", None)) or ""
    if tool_call_id and tool_name and isinstance(arguments, dict):
        return {
            "kind": "function_call",
            "payload": {
                "type": "function_call",
                "call_id": tool_call_id,
                "name": tool_name,
                "arguments": dict(arguments),
            },
        }
    if role == "tool" or (
        tool_call_id
        and tool_name is None
        and arguments in (None, "", {}, [])
    ):
        return {
            "kind": "function_call_output",
            "payload": {
                "type": "function_call_output",
                "call_id": tool_call_id or "",
                "output": content if content is not None else text,
            },
        }
    if role not in {"user", "assistant", "system"}:
        role = "user"
    return {
        "kind": "message",
        "payload": {
            "role": role,
            "content": content if content is not None else text,
        },
    }


def _role_from_context_slice_item(item: object) -> str | None:
    kind = str(getattr(item, "kind", "") or "").strip()
    title = str(getattr(item, "title", "") or "").strip().lower()
    if kind == "user_message" or title.startswith("user"):
        return "user"
    if kind == "assistant_message" or title.startswith("assistant"):
        return "assistant"
    if kind == "tool_result" or title.startswith("tool"):
        return "tool"
    return None


def _context_slice_collapsed_refs(context_slice: object | None) -> tuple[dict[str, object], ...]:
    if context_slice is None:
        return ()
    report = getattr(context_slice, "report", None)
    collapsed_refs = getattr(report, "collapsed_refs", ()) if report else ()
    if not isinstance(collapsed_refs, (list, tuple)):
        return ()
    return tuple(dict(ref) for ref in collapsed_refs if isinstance(ref, dict))


def _context_slice_report_refs(
    context_slice: object | None,
) -> dict[str, tuple[dict[str, object], ...]]:
    report = getattr(context_slice, "report", None) if context_slice is not None else None
    return {
        "archived_refs": _context_slice_report_ref_tuple(report, "archived_refs"),
        "redacted_refs": _context_slice_report_ref_tuple(report, "redacted_refs"),
        "unresolved_refs": _context_slice_report_ref_tuple(report, "unresolved_refs"),
    }


def _context_slice_report_ref_tuple(
    report: object | None,
    attribute: str,
) -> tuple[dict[str, object], ...]:
    refs = getattr(report, attribute, ()) if report is not None else ()
    if not isinstance(refs, (list, tuple)):
        return ()
    return tuple(dict(ref) for ref in refs if isinstance(ref, dict))


def _context_slice_loss(context_slice: object | None) -> dict[str, object]:
    report = getattr(context_slice, "report", None) if context_slice is not None else None
    loss = getattr(report, "loss", {}) if report is not None else {}
    if not isinstance(loss, dict):
        return {}
    return {
        str(key): value
        for key, value in loss.items()
        if value not in (None, "", {}, [])
    }


def _context_slice_tool_schemas(
    context_slice: object | None,
    *,
    available_schemas: tuple[ToolSchema, ...] = (),
) -> tuple[ToolSchema, ...]:
    if context_slice is None:
        return ()
    active_names = _context_slice_active_tool_names(context_slice)
    if not active_names:
        return ()
    schemas: list[ToolSchema] = []
    seen: set[str] = set()
    for schema in available_schemas:
        if schema.name not in active_names:
            continue
        if schema.name in seen:
            continue
        schemas.append(schema)
        seen.add(schema.name)
    return tuple(schemas)


def _context_slice_tool_schema_refs(
    context_slice: object | None,
    *,
    schemas: tuple[ToolSchema, ...] = (),
) -> tuple[dict[str, object], ...]:
    if context_slice is None:
        return ()
    tool_ref_by_name: dict[str, object] = {}
    for tool_ref in getattr(context_slice, "active_tools", ()) or ():
        raw_name = getattr(tool_ref, "function_name", None)
        name = raw_name.strip() if isinstance(raw_name, str) else ""
        if name and name not in tool_ref_by_name:
            tool_ref_by_name[name] = tool_ref
    refs: list[dict[str, object]] = []
    seen: set[str] = set()
    for schema in schemas:
        if schema.name in seen:
            continue
        tool_ref = tool_ref_by_name.get(schema.name)
        if tool_ref is None:
            continue
        owner_ref = getattr(tool_ref, "owner_ref", None)
        refs.append(
            {
                key: value
                for key, value in {
                    "name": schema.name,
                    "source": "context_slice",
                    "schema": schema.to_payload(),
                    "node_id": getattr(tool_ref, "node_id", None),
                    "tool_ref_id": getattr(tool_ref, "tool_ref_id", None),
                    "source_id": getattr(tool_ref, "source_id", None),
                    "function_name": getattr(tool_ref, "function_name", None),
                    "owner_ref": (
                        dict(owner_ref) if isinstance(owner_ref, dict) else None
                    ),
                }.items()
                if value not in (None, "", {}, [])
            },
        )
        seen.add(schema.name)
    return tuple(refs)


def _context_slice_active_tool_names(
    context_slice: object | None,
) -> frozenset[str]:
    if context_slice is None:
        return frozenset()
    names: set[str] = set()
    for tool_ref in getattr(context_slice, "active_tools", ()) or ():
        name = getattr(tool_ref, "function_name", None)
        if isinstance(name, str) and name.strip():
            names.add(name.strip())
    return frozenset(names)


def _ref_counts(
    refs: tuple[dict[str, object], ...],
    key: str,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ref in refs:
        raw_value = ref.get(key)
        value = raw_value.strip() if isinstance(raw_value, str) else ""
        if not value:
            value = "unknown"
        counts[value] = counts.get(value, 0) + 1
    return counts


def _snapshot_payload_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return dict(value)


def _request_render_tool_schemas(
    schemas: tuple[ToolSchema, ...],
    *,
    render_metadata: dict[str, object],
    tree_service: ContextTreeService | None,
    session_key: str,
    surface_contract: str = "default_open",
    active_tool_names: frozenset[str] = frozenset(),
) -> tuple[ToolSchema, ...]:
    if surface_contract == "declared_only":
        return _dedupe_tool_schemas(schemas)
    if tree_service is None and not render_metadata:
        return _dedupe_tool_schemas(schemas)
    default_schema_ids = _metadata_string_set(
        render_metadata.get("default_tool_schema_ids"),
    )
    enabled_schema_names = _enabled_tool_schema_names(
        tree_service=tree_service,
        session_key=session_key,
    )
    visible_names = {
        "capability.search",
        *default_schema_ids,
        *enabled_schema_names,
        *active_tool_names,
    }
    selected: list[ToolSchema] = []
    seen: set[str] = set()
    for schema in schemas:
        name = schema.name.strip()
        if not name or name in seen:
            continue
        if name not in visible_names:
            continue
        selected.append(schema)
        seen.add(name)
    return tuple(selected)


def _dedupe_tool_schemas(schemas: tuple[ToolSchema, ...]) -> tuple[ToolSchema, ...]:
    selected: list[ToolSchema] = []
    seen: set[str] = set()
    for schema in schemas:
        name = schema.name.strip()
        if not name or name in seen:
            continue
        selected.append(schema)
        seen.add(name)
    return tuple(selected)


def _enabled_tool_schema_names(
    *,
    tree_service: ContextTreeService | None,
    session_key: str,
) -> frozenset[str]:
    if tree_service is None:
        return frozenset()
    try:
        return frozenset(tree_service.list_enabled_tool_schema_names(session_key))
    except Exception:
        return frozenset()


def _sync_requested_tool_schema_nodes(
    *,
    tree_service: ContextTreeService | None,
    session_key: str,
    run_id: str,
    schema_names: tuple[str, ...],
    render_metadata: dict[str, object],
) -> None:
    if tree_service is None:
        return
    requested_names = frozenset(
        name.strip()
        for name in schema_names
        if isinstance(name, str) and name.strip()
    )
    if not requested_names:
        return
    tree_service.list_tree(session_key, refresh=True)
    _expand_context_node_if_present(
        tree_service=tree_service,
        session_key=session_key,
        run_id=run_id,
        node_id="tools.available",
    )
    _expand_tool_groups_from_render_metadata(
        tree_service=tree_service,
        session_key=session_key,
        run_id=run_id,
        render_metadata=render_metadata,
    )
    _expand_tool_groups_for_schema_names(
        tree_service=tree_service,
        session_key=session_key,
        run_id=run_id,
        schema_names=requested_names,
    )
    for node in tree_service.list_tool_nodes_by_kind(
        session_key,
        kinds=("tool_function",),
    ):
        name = _tool_node_function_name(node)
        if name not in requested_names:
            continue
        if node.state.schema_enabled or not node.supports(
            ContextAction.ENABLE_TOOL_SCHEMA,
        ):
            continue
        tree_service.apply_action(
            ContextActionInput(
                session_key=session_key,
                run_id=run_id,
                node_id=node.id,
                action=ContextAction.ENABLE_TOOL_SCHEMA,
            ),
        )


def _expand_tool_groups_from_render_metadata(
    *,
    tree_service: ContextTreeService,
    session_key: str,
    run_id: str,
    render_metadata: dict[str, object],
) -> None:
    bundle_nodes = tree_service.list_tool_nodes_by_kind(
        session_key,
        kinds=("tool_bundle",),
    )
    group_nodes = tree_service.list_tool_nodes_by_kind(
        session_key,
        kinds=("tool_bundle_group",),
    )
    for raw_ref in (
        *_metadata_dict_list(render_metadata.get("default_tool_schema_group_matches")),
        *_metadata_dict_list(render_metadata.get("default_tool_schema_group_refs")),
    ):
        node_id = _metadata_text_value(raw_ref.get("node_id"))
        source_id = _metadata_text_value(raw_ref.get("source_id"))
        if source_id is not None:
            bundle_node = next(
                (
                    node
                    for node in bundle_nodes
                    if _metadata_text_value(
                        node.owner_ref.get("source_id"),
                        node.metadata.get("source_id"),
                    )
                    == source_id
                ),
                None,
            )
            if bundle_node is not None:
                _expand_context_node_if_present(
                    tree_service=tree_service,
                    session_key=session_key,
                    run_id=run_id,
                    node_id=bundle_node.id,
                )
        if node_id is not None:
            _expand_context_node_if_present(
                tree_service=tree_service,
                session_key=session_key,
                run_id=run_id,
                node_id=node_id,
            )
            continue
        group_key = _metadata_text_value(raw_ref.get("group_key"))
        if source_id is None or group_key is None:
            continue
        group_nodes = tree_service.list_tool_nodes_by_kind(
            session_key,
            kinds=("tool_bundle_group",),
        )
        group_node = next(
            (
                node
                for node in group_nodes
                if _metadata_text_value(
                    node.owner_ref.get("source_id"),
                    node.metadata.get("source_id"),
                )
                == source_id
                and _metadata_text_value(
                    node.owner_ref.get("group_key"),
                    node.metadata.get("group_key"),
                )
                == group_key
            ),
            None,
        )
        if group_node is not None:
            _expand_context_node_if_present(
                tree_service=tree_service,
                session_key=session_key,
                run_id=run_id,
                node_id=group_node.id,
            )


def _expand_tool_groups_for_schema_names(
    *,
    tree_service: ContextTreeService,
    session_key: str,
    run_id: str,
    schema_names: frozenset[str],
) -> None:
    if _tool_function_nodes_include(
        tree_service=tree_service,
        session_key=session_key,
        schema_names=schema_names,
    ):
        return
    source_ids = _schema_source_ids(schema_names)
    bundle_nodes = tree_service.list_tool_nodes_by_kind(
        session_key,
        kinds=("tool_bundle",),
    )
    for node in bundle_nodes:
        source_id = _metadata_text_value(
            node.owner_ref.get("source_id"),
            node.metadata.get("source_id"),
        )
        if source_ids and source_id not in source_ids:
            continue
        _expand_context_node_if_present(
            tree_service=tree_service,
            session_key=session_key,
            run_id=run_id,
            node_id=node.id,
        )
    group_nodes = tree_service.list_tool_nodes_by_kind(
        session_key,
        kinds=("tool_bundle_group",),
    )
    for node in group_nodes:
        function_names = set(
            _metadata_string_values(node.owner_ref.get("function_ids")),
        )
        function_names.update(_metadata_string_values(node.metadata.get("function_ids")))
        function_names.update(
            _metadata_string_values(node.metadata.get("default_tool_schema_ids")),
        )
        if function_names and schema_names.isdisjoint(function_names):
            continue
        source_id = _metadata_text_value(
            node.owner_ref.get("source_id"),
            node.metadata.get("source_id"),
        )
        if not function_names and source_ids and source_id not in source_ids:
            continue
        _expand_context_node_if_present(
            tree_service=tree_service,
            session_key=session_key,
            run_id=run_id,
            node_id=node.id,
        )


def _tool_function_nodes_include(
    *,
    tree_service: ContextTreeService,
    session_key: str,
    schema_names: frozenset[str],
) -> bool:
    return any(
        _tool_node_function_name(node) in schema_names
        for node in tree_service.list_tool_nodes_by_kind(
            session_key,
            kinds=("tool_function",),
        )
    )


def _expand_context_node_if_present(
    *,
    tree_service: ContextTreeService,
    session_key: str,
    run_id: str,
    node_id: str,
) -> None:
    node = tree_service.get_node(session_key, node_id)
    if node is None or not node.state.collapsed or not node.supports(ContextAction.EXPAND):
        return
    tree_service.apply_action(
        ContextActionInput(
            session_key=session_key,
            run_id=run_id,
            node_id=node_id,
            action=ContextAction.EXPAND,
        ),
    )


def _tool_node_function_name(node: object) -> str | None:
    owner_ref = getattr(node, "owner_ref", {})
    metadata = getattr(node, "metadata", {})
    if not isinstance(owner_ref, dict):
        owner_ref = {}
    if not isinstance(metadata, dict):
        metadata = {}
    return _metadata_text_value(
        owner_ref.get("tool_id"),
        owner_ref.get("function_id"),
        metadata.get("function_name"),
    )


def _metadata_string_values(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple | set | frozenset):
        return ()
    values: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            values.append(item.strip())
    return tuple(values)


def _schema_source_ids(schema_names: frozenset[str]) -> frozenset[str]:
    source_ids: set[str] = set()
    builtin_source_ids = {
        "exec": "bundled.local_package.command",
        "process": "bundled.local_package.command",
    }
    for schema_name in schema_names:
        builtin_source_id = builtin_source_ids.get(schema_name)
        if builtin_source_id is not None:
            source_ids.add(builtin_source_id)
            continue
        namespace, _, _operation = schema_name.partition("_")
        if not namespace:
            continue
        source_ids.add(f"bundled.local_package.{namespace}")
        source_ids.add(f"bundled.openapi.{namespace}")
    return frozenset(source_ids)


def _request_session_item_max_chars(draft: RuntimeLlmRequestDraft) -> int | None:
    mode = getattr(getattr(draft, "mode", None), "value", None)
    if mode not in {"memory_flush", "compaction"}:
        return None
    report = getattr(draft, "report", None)
    if report is None:
        return None
    budget = getattr(report, "transcript_budget", None)
    if not isinstance(budget, dict):
        return None
    value = budget.get("max_chars")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _metadata_text_value(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _metadata_string_set(value: object) -> frozenset[str]:
    if not isinstance(value, list | tuple | set | frozenset):
        return frozenset()
    return frozenset(
        text
        for item in value
        if isinstance(item, str) and (text := item.strip())
    )


__all__ = ["ContextWorkspaceRunSnapshotAdapter"]
