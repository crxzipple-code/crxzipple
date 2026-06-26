from __future__ import annotations

from crxzipple.modules.context_workspace.application.context_tree_maintenance import (
    ensure_default_root_nodes,
    refresh_owner_children,
)
from crxzipple.modules.context_workspace.application.models import (
    ContextDebugDeltaInput,
    ContextDebugDeltaResult,
    ContextObservationRenderInput,
    ContextObservationRenderResult,
    RecordContextSnapshotInput,
    RecordRequestRenderSnapshotInput,
)
from crxzipple.modules.context_workspace.application.ports import ContextOwnerRegistry
from crxzipple.modules.context_workspace.application.rendering import (
    ContextTreeRenderPipeline,
    snapshot_metadata_defaults,
)
from crxzipple.modules.context_workspace.domain import (
    ContextNodeRepository,
    ContextRequestRenderSnapshot,
    ContextRequestRenderSnapshotRepository,
    ContextSnapshot,
    ContextSnapshotNotFoundError,
    ContextSnapshotRepository,
    ContextWorkspace,
    ContextWorkspaceNotFoundError,
    ContextWorkspaceRepository,
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
