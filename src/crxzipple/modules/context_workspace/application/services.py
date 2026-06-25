from __future__ import annotations

from time import perf_counter

from crxzipple.modules.context_workspace.application.models import (
    BuildContextControlSliceInput,
    BuildContextObservationSliceInput,
    ContextActionInput,
    ContextActionResult,
    ContextControlSlice,
    ContextNodeUpsertInput,
    ContextNodeUpsertResult,
    ContextSlice,
    ContextTreeView,
    EnsureContextWorkspaceInput,
    RecordContextSnapshotInput,
    ContextDebugDeltaInput,
    ContextDebugDeltaResult,
    ContextObservationRenderInput,
    ContextObservationRenderResult,
    RecordRequestRenderSnapshotInput,
)
from crxzipple.modules.context_workspace.application.ports import ContextOwnerRegistry
from crxzipple.modules.context_workspace.application.context_control_slice_builder import (
    build_context_control_slice,
)
from crxzipple.modules.context_workspace.application.context_slice_item_projection import (
    SessionItemResolver,
)
from crxzipple.modules.context_workspace.application.context_slice_selection import (
    normalize_slice_audience,
    visible_nodes_for_slice,
)
from crxzipple.modules.context_workspace.application.context_tool_surface_projection import (
    tool_function_name,
)
from crxzipple.modules.context_workspace.application.context_observation_slice_builder import (
    build_context_observation_slice,
)
from crxzipple.modules.context_workspace.application.context_tree_actions import (
    ContextTreeActionService,
)
from crxzipple.modules.context_workspace.application.context_tree_maintenance import (
    ensure_default_root_nodes,
    load_owner_children,
    prune_orphan_nodes,
    refresh_owner_children,
)
from crxzipple.modules.context_workspace.application.rendering import (
    ContextTreeRenderPipeline,
    aggregate_estimate,
    snapshot_metadata_defaults,
)
from crxzipple.modules.context_workspace.domain import (
    ContextNode,
    ContextNodeRepository,
    ContextOperationRepository,
    ContextSnapshot,
    ContextSnapshotNotFoundError,
    ContextSnapshotRepository,
    ContextRequestRenderSnapshot,
    ContextRequestRenderSnapshotRepository,
    ContextWorkspace,
    ContextWorkspaceNotFoundError,
    ContextWorkspaceRepository,
)


class ContextWorkspaceService:
    def __init__(
        self,
        *,
        workspace_repository: ContextWorkspaceRepository,
        node_repository: ContextNodeRepository,
        owner_registry: ContextOwnerRegistry | None = None,
    ) -> None:
        self._workspaces = workspace_repository
        self._nodes = node_repository
        self._owner_registry = owner_registry

    def ensure_workspace(
        self,
        data: EnsureContextWorkspaceInput,
    ) -> ContextWorkspace:
        workspace = self._workspaces.get_by_session(data.session_key)
        if workspace is None:
            workspace = ContextWorkspace.new(
                session_key=data.session_key,
                agent_id=data.agent_id,
                metadata=data.metadata,
            )
            self._workspaces.add(workspace)
        else:
            changed = False
            if workspace.agent_id != data.agent_id:
                workspace.agent_id = data.agent_id
                changed = True
            for key, value in data.metadata.items():
                if workspace.metadata.get(key) != value:
                    workspace.metadata[key] = value
                    changed = True
            if changed:
                workspace.touch_revision()
                self._workspaces.save(workspace)
        self._ensure_default_root_nodes(workspace)
        if data.refresh_expanded_children:
            self._refresh_expanded_children(workspace)
        return workspace

    def get_by_session(self, session_key: str) -> ContextWorkspace:
        workspace = self._workspaces.get_by_session(session_key)
        if workspace is None:
            raise ContextWorkspaceNotFoundError(
                f"Context workspace for session '{session_key}' was not found.",
            )
        return workspace

    def get(self, workspace_id: str) -> ContextWorkspace:
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise ContextWorkspaceNotFoundError(
                f"Context workspace '{workspace_id}' was not found.",
            )
        return workspace

    def list_workspaces(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[ContextWorkspace, ...]:
        return self._workspaces.list_recent(
            limit=max(1, min(int(limit), 500)),
            offset=max(0, int(offset)),
        )

    def _ensure_default_root_nodes(self, workspace: ContextWorkspace) -> None:
        ensure_default_root_nodes(
            workspace=workspace,
            node_repository=self._nodes,
        )

    def _refresh_expanded_children(self, workspace: ContextWorkspace) -> None:
        refresh_owner_children(
            workspace=workspace,
            node_repository=self._nodes,
            owner_registry=self._owner_registry,
        )

    def _prune_orphan_nodes(self, workspace: ContextWorkspace) -> None:
        prune_orphan_nodes(
            workspace=workspace,
            node_repository=self._nodes,
        )

    def _load_owner_children(
        self,
        workspace: ContextWorkspace,
        node: ContextNode,
    ) -> None:
        load_owner_children(
            workspace=workspace,
            node=node,
            node_repository=self._nodes,
            owner_registry=self._owner_registry,
        )


class ContextTreeService:
    def __init__(
        self,
        *,
        workspace_repository: ContextWorkspaceRepository,
        node_repository: ContextNodeRepository,
        operation_repository: ContextOperationRepository,
        owner_registry: ContextOwnerRegistry | None = None,
    ) -> None:
        self._workspaces = workspace_repository
        self._nodes = node_repository
        self._owner_registry = owner_registry
        self._actions = ContextTreeActionService(
            workspace_repository=workspace_repository,
            node_repository=node_repository,
            operation_repository=operation_repository,
            owner_registry=owner_registry,
        )

    def list_tree(self, session_key: str, *, refresh: bool = True) -> ContextTreeView:
        workspace = self._require_workspace(session_key)
        ensure_default_root_nodes(
            workspace=workspace,
            node_repository=self._nodes,
        )
        if refresh:
            refresh_owner_children(
                workspace=workspace,
                node_repository=self._nodes,
                owner_registry=self._owner_registry,
                preload_only=True,
            )
        nodes = self._nodes.list_for_workspace(workspace.id)
        return ContextTreeView(
            workspace=workspace,
            nodes=nodes,
            estimate=aggregate_estimate(nodes),
        )

    def get_node(self, session_key: str, node_id: str) -> ContextNode | None:
        workspace = self._require_workspace(session_key)
        ensure_default_root_nodes(
            workspace=workspace,
            node_repository=self._nodes,
        )
        return self._nodes.get(workspace_id=workspace.id, node_id=node_id)

    def list_enabled_tool_schema_names(self, session_key: str) -> tuple[str, ...]:
        workspace = self._require_workspace(session_key)
        names: list[str] = []
        seen: set[str] = set()
        for node in self._nodes.list_enabled_tool_schema_nodes(workspace.id):
            name = tool_function_name(node)
            if not isinstance(name, str) or not name.strip():
                continue
            normalized = name.strip()
            if normalized in seen:
                continue
            names.append(normalized)
            seen.add(normalized)
        return tuple(names)

    def list_tool_nodes_by_kind(
        self,
        session_key: str,
        *,
        kinds: tuple[str, ...],
    ) -> tuple[ContextNode, ...]:
        workspace = self._require_workspace(session_key)
        return self._nodes.list_tool_nodes_by_kind(
            workspace.id,
            kinds=kinds,
        )

    def apply_action(self, data: ContextActionInput) -> ContextActionResult:
        return self._actions.apply_action(data)

    def upsert_nodes(self, data: ContextNodeUpsertInput) -> ContextNodeUpsertResult:
        return self._actions.upsert_nodes(data)

    def _require_workspace(self, session_key: str) -> ContextWorkspace:
        workspace = self._workspaces.get_by_session(session_key)
        if workspace is None:
            raise ContextWorkspaceNotFoundError(
                f"Context workspace for session '{session_key}' was not found.",
            )
        return workspace

    def _load_owner_children(
        self,
        workspace: ContextWorkspace,
        node: ContextNode,
    ) -> None:
        load_owner_children(
            workspace=workspace,
            node=node,
            node_repository=self._nodes,
            owner_registry=self._owner_registry,
        )


class ContextObservationSnapshotService:
    def __init__(
        self,
        *,
        workspace_repository: ContextWorkspaceRepository,
        node_repository: ContextNodeRepository,
        snapshot_repository: ContextSnapshotRepository,
        owner_registry: ContextOwnerRegistry | None = None,
    ) -> None:
        self._workspaces = workspace_repository
        self._nodes = node_repository
        self._snapshots = snapshot_repository
        self._owner_registry = owner_registry
        self._pipeline = ContextTreeRenderPipeline()

    def render_observation(
        self,
        data: ContextObservationRenderInput,
    ) -> ContextObservationRenderResult:
        workspace = self._require_workspace(data.session_key)
        ensure_default_root_nodes(
            workspace=workspace,
            node_repository=self._nodes,
        )
        refresh_owner_children(
            workspace=workspace,
            node_repository=self._nodes,
            owner_registry=self._owner_registry,
        )
        nodes = self._nodes.list_for_workspace(workspace.id)
        return self._pipeline.render_observation(
            workspace=workspace,
            nodes=nodes,
            provider_attachments=data.provider_attachments,
            metadata=data.metadata,
        )

    def render_delta(
        self,
        data: ContextDebugDeltaInput,
    ) -> ContextDebugDeltaResult:
        baseline = self.get_snapshot(data.baseline_snapshot_id)
        current = self.render_observation(
            ContextObservationRenderInput(
                session_key=data.session_key,
                run_id=data.run_id,
                provider_attachments=data.provider_attachments,
                metadata=data.metadata,
            ),
        )
        return self._pipeline.render_delta(
            workspace=current.workspace,
            baseline=baseline,
            current=current,
            metadata=data.metadata,
        )

    def record_snapshot(
        self,
        data: RecordContextSnapshotInput,
    ) -> ContextSnapshot:
        workspace = self._require_workspace(data.session_key)
        metadata = (
            snapshot_metadata_defaults(
                data.metadata,
                nodes=self._nodes.list_for_workspace(workspace.id),
            )
            if data.include_metadata_defaults
            else dict(data.metadata)
        )
        snapshot = ContextSnapshot(
            id=data.snapshot_id,
            workspace_id=workspace.id,
            session_key=workspace.session_key,
            run_id=data.run_id,
            tree_revision=workspace.active_revision,
            debug_body=data.debug_body,
            provider_attachments=data.provider_attachments,
            estimate=data.estimate,
            included_node_ids=data.included_node_ids,
            mirrored_node_ids=data.mirrored_node_ids,
            included_refs=data.included_refs,
            collapsed_refs=data.collapsed_refs,
            protocol_required_refs=data.protocol_required_refs,
            metadata=metadata,
            parent_snapshot_id=data.parent_snapshot_id,
            parent_tree_revision=data.parent_tree_revision,
        )
        self._snapshots.add(snapshot)
        return snapshot

    def get_snapshot_by_run(self, run_id: str) -> ContextSnapshot:
        snapshot = self._snapshots.get_by_run(run_id)
        if snapshot is None:
            raise ContextSnapshotNotFoundError(
                f"Context snapshot for run '{run_id}' was not found.",
            )
        return snapshot

    def get_snapshot(self, snapshot_id: str) -> ContextSnapshot:
        snapshot = self._snapshots.get(snapshot_id)
        if snapshot is None:
            raise ContextSnapshotNotFoundError(
                f"Context snapshot '{snapshot_id}' was not found.",
            )
        return snapshot

    def list_recent_snapshots(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[ContextSnapshot, ...]:
        return self._snapshots.list_recent(
            limit=max(1, min(int(limit), 500)),
            offset=max(0, int(offset)),
        )

    def _require_workspace(self, session_key: str) -> ContextWorkspace:
        workspace = self._workspaces.get_by_session(session_key)
        if workspace is None:
            raise ContextWorkspaceNotFoundError(
                f"Context workspace for session '{session_key}' was not found.",
            )
        return workspace


class RequestRenderSnapshotService:
    def __init__(
        self,
        *,
        workspace_repository: ContextWorkspaceRepository,
        snapshot_repository: ContextRequestRenderSnapshotRepository,
    ) -> None:
        self._workspaces = workspace_repository
        self._snapshots = snapshot_repository

    def record_snapshot(
        self,
        data: RecordRequestRenderSnapshotInput,
    ) -> ContextRequestRenderSnapshot:
        workspace_id = data.workspace_id
        if workspace_id is None or not workspace_id.strip():
            workspace = self._workspaces.get_by_session(data.session_key)
            if workspace is None:
                raise ContextWorkspaceNotFoundError(
                    f"Context workspace for session '{data.session_key}' was not found.",
                )
            workspace_id = workspace.id
        snapshot = ContextRequestRenderSnapshot(
            id=data.snapshot_id,
            workspace_id=workspace_id,
            session_key=data.session_key,
            run_id=data.run_id,
            tree_revision=data.tree_revision,
            turn_id=data.turn_id,
            step_id=data.step_id,
            llm_invocation_id=data.llm_invocation_id,
            provider=data.provider,
            transport=data.transport,
            model=data.model,
            renderer_id=data.renderer_id,
            renderer_version=data.renderer_version,
            session_frontier_revision=data.session_frontier_revision,
            input_item_refs=data.input_item_refs,
            projected_input_items=data.projected_input_items,
            tool_schema_refs=data.tool_schema_refs,
            resource_refs=data.resource_refs,
            request_hash=data.request_hash,
            estimated_tokens=data.estimated_tokens,
            render_report=data.render_report,
            timings=data.timings,
            metadata=data.metadata,
        )
        self._snapshots.add(snapshot)
        return snapshot

    def get_snapshot(self, snapshot_id: str) -> ContextRequestRenderSnapshot:
        snapshot = self._snapshots.get(snapshot_id)
        if snapshot is None:
            raise ContextSnapshotNotFoundError(
                f"Context request render snapshot '{snapshot_id}' was not found.",
            )
        return snapshot

    def get_snapshot_by_run(self, run_id: str) -> ContextRequestRenderSnapshot:
        snapshot = self._snapshots.get_by_run(run_id)
        if snapshot is None:
            raise ContextSnapshotNotFoundError(
                f"Context request render snapshot for run '{run_id}' was not found.",
            )
        return snapshot

    def list_recent_snapshots(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[ContextRequestRenderSnapshot, ...]:
        return self._snapshots.list_recent(
            limit=max(1, min(int(limit), 500)),
            offset=max(0, int(offset)),
        )


class ContextSliceBuilderService:
    def __init__(
        self,
        *,
        workspace_repository: ContextWorkspaceRepository,
        node_repository: ContextNodeRepository,
        owner_registry: ContextOwnerRegistry | None = None,
        session_item_resolver: SessionItemResolver | None = None,
    ) -> None:
        self._workspaces = workspace_repository
        self._nodes = node_repository
        self._owner_registry = owner_registry
        self._session_item_resolver = session_item_resolver

    def build_slice(
        self,
        *,
        session_key: str = "",
        run_id: str = "",
        audience: str = "llm_request",
        provider_profile: str | None = None,
        data: BuildContextObservationSliceInput | None = None,
    ) -> ContextSlice:
        if data is not None:
            session_key = data.session_key
            run_id = data.run_id
            audience = data.audience
            provider_profile = data.provider_profile
            request_metadata = dict(data.metadata)
        else:
            request_metadata = {}
        timings_started_at = perf_counter()
        phase_started_at = timings_started_at
        builder_timings: dict[str, float] = {}

        def record_timing(label: str) -> None:
            nonlocal phase_started_at
            now = perf_counter()
            builder_timings[f"{label}_ms"] = round(
                (now - phase_started_at) * 1000,
                3,
            )
            phase_started_at = now

        audience = normalize_slice_audience(audience)
        workspace = self._require_workspace(session_key)
        record_timing("require_workspace")
        read_only = request_metadata.get("read_only") is True
        if not read_only:
            ensure_default_root_nodes(
                workspace=workspace,
                node_repository=self._nodes,
            )
            refresh_owner_children(
                workspace=workspace,
                node_repository=self._nodes,
                owner_registry=self._owner_registry,
            )
        record_timing("refresh_owner_children")
        nodes = self._nodes.list_for_workspace(workspace.id)
        record_timing("list_nodes")
        return build_context_observation_slice(
            workspace=workspace,
            nodes=nodes,
            run_id=run_id,
            audience=audience,
            provider_profile=provider_profile,
            request_metadata=request_metadata,
            read_only=read_only,
            session_item_resolver=self._session_item_resolver,
            builder_timings=builder_timings,
            timings_started_at=timings_started_at,
        )

    def _require_workspace(self, session_key: str) -> ContextWorkspace:
        workspace = self._workspaces.get_by_session(session_key)
        if workspace is None:
            raise ContextWorkspaceNotFoundError(
                f"Context workspace for session '{session_key}' was not found.",
            )
        return workspace


class ContextControlSliceService:
    def __init__(
        self,
        *,
        workspace_repository: ContextWorkspaceRepository,
        node_repository: ContextNodeRepository,
    ) -> None:
        self._workspaces = workspace_repository
        self._nodes = node_repository

    def build_control_slice(
        self,
        *,
        session_key: str = "",
        run_id: str = "",
        audience: str = "llm_request",
        provider_profile: str | None = None,
        data: BuildContextControlSliceInput | None = None,
    ) -> ContextControlSlice:
        if data is not None:
            session_key = data.session_key
            run_id = data.run_id
            audience = data.audience
            provider_profile = data.provider_profile
            request_metadata = dict(data.metadata)
        else:
            request_metadata = {}
        audience = normalize_slice_audience(audience)
        workspace = self._require_workspace(session_key)
        read_only = request_metadata.get("read_only") is True
        if not read_only:
            ensure_default_root_nodes(
                workspace=workspace,
                node_repository=self._nodes,
            )
        nodes = self._nodes.list_for_workspace(workspace.id)
        visible_nodes = visible_nodes_for_slice(nodes, audience=audience)
        return build_context_control_slice(
            workspace=workspace,
            nodes=nodes,
            visible_nodes=visible_nodes,
            run_id=run_id,
            audience=audience,
            provider_profile=provider_profile,
            request_metadata=request_metadata,
            read_only=read_only,
        )

    def _require_workspace(self, session_key: str) -> ContextWorkspace:
        workspace = self._workspaces.get_by_session(session_key)
        if workspace is None:
            raise ContextWorkspaceNotFoundError(
                f"Context workspace for session '{session_key}' was not found.",
            )
        return workspace


__all__ = [
    "ContextControlSliceService",
    "ContextSliceBuilderService",
    "ContextObservationSnapshotService",
    "ContextTreeService",
    "ContextWorkspaceService",
]
