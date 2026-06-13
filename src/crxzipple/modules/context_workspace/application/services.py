from __future__ import annotations

from uuid import uuid4

from crxzipple.modules.context_workspace.application import root_nodes
from crxzipple.modules.context_workspace.application.models import (
    ContextActionInput,
    ContextActionResult,
    ContextNodeUpsertInput,
    ContextNodeUpsertResult,
    ContextTreeView,
    EnsureContextWorkspaceInput,
    RecordContextRenderSnapshotInput,
    RenderContextDeltaInput,
    RenderContextDeltaResult,
    RenderContextPromptInput,
    RenderContextPromptResult,
)
from crxzipple.modules.context_workspace.application.ports import (
    ContextChildrenRequest,
    ContextOwnerRegistry,
)
from crxzipple.modules.context_workspace.application.rendering import (
    ContextRenderPipeline,
    aggregate_estimate,
    render_snapshot_metadata_defaults,
)
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextActionNotAllowedError,
    ContextNode,
    ContextNodeNotFoundError,
    ContextNodeRepository,
    ContextNodeSeed,
    ContextNodeState,
    ContextOperationRepository,
    ContextRenderSnapshot,
    ContextRenderSnapshotNotFoundError,
    ContextRenderSnapshotRepository,
    ContextTreeOperation,
    ContextWorkspace,
    ContextWorkspaceNotFoundError,
    ContextWorkspaceRepository,
)


_SCHEMA_ENABLED_SOURCE_KEY = "schema_enabled_source"
_SCHEMA_ENABLED_SOURCE_ACTION = "context_tree_action"


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
        _ensure_default_root_nodes(
            workspace=workspace,
            node_repository=self._nodes,
        )

    def _refresh_expanded_children(self, workspace: ContextWorkspace) -> None:
        _refresh_owner_children(
            workspace=workspace,
            node_repository=self._nodes,
            owner_registry=self._owner_registry,
        )

    def _prune_orphan_nodes(self, workspace: ContextWorkspace) -> None:
        _prune_orphan_nodes(
            workspace=workspace,
            node_repository=self._nodes,
        )

    def _load_owner_children(
        self,
        workspace: ContextWorkspace,
        node: ContextNode,
    ) -> None:
        _load_owner_children(
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
        self._operations = operation_repository
        self._owner_registry = owner_registry

    def list_tree(self, session_key: str, *, refresh: bool = True) -> ContextTreeView:
        workspace = self._require_workspace(session_key)
        _ensure_default_root_nodes(
            workspace=workspace,
            node_repository=self._nodes,
        )
        if refresh:
            _refresh_owner_children(
                workspace=workspace,
                node_repository=self._nodes,
                owner_registry=self._owner_registry,
            )
        nodes = self._nodes.list_for_workspace(workspace.id)
        return ContextTreeView(
            workspace=workspace,
            nodes=nodes,
            estimate=aggregate_estimate(nodes),
        )

    def get_node(self, session_key: str, node_id: str) -> ContextNode | None:
        workspace = self._require_workspace(session_key)
        _ensure_default_root_nodes(
            workspace=workspace,
            node_repository=self._nodes,
        )
        return self._nodes.get(workspace_id=workspace.id, node_id=node_id)

    def apply_action(self, data: ContextActionInput) -> ContextActionResult:
        workspace = self._require_workspace(data.session_key)
        node = self._nodes.get(workspace_id=workspace.id, node_id=data.node_id)
        if node is None:
            raise ContextNodeNotFoundError(
                f"Context node '{data.node_id}' was not found.",
            )
        if not node.supports(data.action):
            raise ContextActionNotAllowedError(
                f"Context node '{data.node_id}' does not support action '{data.action.value}'.",
            )
        node.apply_state(_state_after_action(node.state, data.action))
        _record_schema_enabled_action(node, data)
        if data.action is ContextAction.EXPAND:
            self._load_owner_children(workspace, node)
        workspace.touch_revision()
        self._nodes.save(node)
        self._workspaces.save(workspace)
        operation = ContextTreeOperation(
            id=f"ctxop_{uuid4().hex}",
            workspace_id=workspace.id,
            session_key=workspace.session_key,
            run_id=data.run_id,
            node_id=node.id,
            action=data.action,
            actor=data.actor,
            status="succeeded",
            payload=data.payload,
            result={"state": node.state.to_payload()},
            tree_revision=workspace.active_revision,
        )
        self._operations.add(operation)
        return ContextActionResult(
            workspace=workspace,
            node=node,
            action=data.action,
            operation_id=operation.id,
        )

    def upsert_nodes(self, data: ContextNodeUpsertInput) -> ContextNodeUpsertResult:
        workspace = self._require_workspace(data.session_key)
        nodes = _children_from_seeds(
            workspace=workspace,
            seeds=data.nodes,
            node_repository=self._nodes,
            preserve_existing_state=False,
        )
        self._nodes.save_many(nodes)
        workspace.touch_revision()
        self._workspaces.save(workspace)
        operation = ContextTreeOperation(
            id=f"ctxop_{uuid4().hex}",
            workspace_id=workspace.id,
            session_key=workspace.session_key,
            run_id=data.run_id,
            node_id=data.parent_node_id,
            action=data.action,
            actor=data.actor,
            status="succeeded",
            payload=data.payload,
            result={"node_ids": [node.id for node in nodes]},
            tree_revision=workspace.active_revision,
        )
        self._operations.add(operation)
        return ContextNodeUpsertResult(
            workspace=workspace,
            nodes=nodes,
            action=data.action,
            operation_id=operation.id,
        )

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
        _load_owner_children(
            workspace=workspace,
            node=node,
            node_repository=self._nodes,
            owner_registry=self._owner_registry,
        )


class ContextRenderService:
    def __init__(
        self,
        *,
        workspace_repository: ContextWorkspaceRepository,
        node_repository: ContextNodeRepository,
        snapshot_repository: ContextRenderSnapshotRepository,
        owner_registry: ContextOwnerRegistry | None = None,
    ) -> None:
        self._workspaces = workspace_repository
        self._nodes = node_repository
        self._snapshots = snapshot_repository
        self._owner_registry = owner_registry
        self._pipeline = ContextRenderPipeline()

    def render_prompt_body(
        self,
        data: RenderContextPromptInput,
    ) -> RenderContextPromptResult:
        workspace = self._require_workspace(data.session_key)
        _ensure_default_root_nodes(
            workspace=workspace,
            node_repository=self._nodes,
        )
        _refresh_owner_children(
            workspace=workspace,
            node_repository=self._nodes,
            owner_registry=self._owner_registry,
        )
        nodes = self._nodes.list_for_workspace(workspace.id)
        return self._pipeline.render_prompt_body(
            workspace=workspace,
            nodes=nodes,
            provider_attachments=data.provider_attachments,
            metadata=data.metadata,
        )

    def render_delta(
        self,
        data: RenderContextDeltaInput,
    ) -> RenderContextDeltaResult:
        baseline = self.get_snapshot(data.baseline_snapshot_id)
        current = self.render_prompt_body(
            RenderContextPromptInput(
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

    def record_render_snapshot(
        self,
        data: RecordContextRenderSnapshotInput,
    ) -> ContextRenderSnapshot:
        workspace = self._require_workspace(data.session_key)
        metadata = render_snapshot_metadata_defaults(
            data.metadata,
            nodes=self._nodes.list_for_workspace(workspace.id),
        )
        snapshot = ContextRenderSnapshot(
            id=data.snapshot_id,
            workspace_id=workspace.id,
            session_key=workspace.session_key,
            run_id=data.run_id,
            tree_revision=workspace.active_revision,
            prompt_body=data.prompt_body,
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

    def get_snapshot_by_run(self, run_id: str) -> ContextRenderSnapshot:
        snapshot = self._snapshots.get_by_run(run_id)
        if snapshot is None:
            raise ContextRenderSnapshotNotFoundError(
                f"Context render snapshot for run '{run_id}' was not found.",
            )
        return snapshot

    def get_snapshot(self, snapshot_id: str) -> ContextRenderSnapshot:
        snapshot = self._snapshots.get(snapshot_id)
        if snapshot is None:
            raise ContextRenderSnapshotNotFoundError(
                f"Context render snapshot '{snapshot_id}' was not found.",
            )
        return snapshot

    def list_recent_snapshots(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[ContextRenderSnapshot, ...]:
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


def _preloads_children(node: ContextNode) -> bool:
    return node.owner == "tool" and node.id == "tools.available"


def _ensure_default_root_nodes(
    *,
    workspace: ContextWorkspace,
    node_repository: ContextNodeRepository,
) -> None:
    nodes = _children_from_seeds(
        workspace=workspace,
        seeds=root_nodes.default_root_node_seeds(
            session_key=workspace.session_key,
            agent_id=workspace.agent_id,
            metadata=workspace.metadata,
        ),
        node_repository=node_repository,
        preserve_existing_dynamic_roots=True,
    )
    if nodes:
        node_repository.save_many(nodes)


_OWNER_CHILD_LOADING_ACTIONS = {
    ContextAction.EXPAND,
}


def _can_load_owner_children(node: ContextNode) -> bool:
    return _preloads_children(node) or any(
        action in _OWNER_CHILD_LOADING_ACTIONS for action in node.actions
    )


def _refresh_owner_children(
    *,
    workspace: ContextWorkspace,
    node_repository: ContextNodeRepository,
    owner_registry: ContextOwnerRegistry | None,
) -> None:
    for node in node_repository.list_for_workspace(workspace.id):
        if node.state.collapsed and not _preloads_children(node):
            continue
        _load_owner_children(
            workspace=workspace,
            node=node,
            node_repository=node_repository,
            owner_registry=owner_registry,
        )
    _prune_orphan_nodes(
        workspace=workspace,
        node_repository=node_repository,
    )


def _load_owner_children(
    *,
    workspace: ContextWorkspace,
    node: ContextNode,
    node_repository: ContextNodeRepository,
    owner_registry: ContextOwnerRegistry | None,
) -> None:
    latest_node = node_repository.get(workspace_id=workspace.id, node_id=node.id)
    if latest_node is None:
        return
    node = latest_node
    if not _can_load_owner_children(node):
        return
    if owner_registry is None:
        return
    provider = owner_registry.get(node.owner)
    if provider is None:
        return
    seeds = provider.children(ContextChildrenRequest(workspace=workspace, node=node))
    keep_node_ids = tuple(seed.node_id for seed in seeds)
    stale_child_ids = tuple(
        child.id
        for child in node_repository.list_for_workspace(workspace.id)
        if child.parent_id == node.id and child.id not in keep_node_ids
    )
    if stale_child_ids:
        node_repository.delete_subtrees(
            workspace_id=workspace.id,
            root_node_ids=stale_child_ids,
        )
    children = _children_from_seeds(
        workspace=workspace,
        seeds=seeds,
        node_repository=node_repository,
    )
    node_repository.save_many(children)
    for child in children:
        if child.state.collapsed and not _preloads_children(child):
            continue
        _load_owner_children(
            workspace=workspace,
            node=child,
            node_repository=node_repository,
            owner_registry=owner_registry,
        )


def _prune_orphan_nodes(
    *,
    workspace: ContextWorkspace,
    node_repository: ContextNodeRepository,
) -> None:
    nodes = node_repository.list_for_workspace(workspace.id)
    node_ids = {node.id for node in nodes}
    orphan_ids = tuple(
        node.id
        for node in nodes
        if node.parent_id is not None and node.parent_id not in node_ids
    )
    if orphan_ids:
        node_repository.delete_subtrees(
            workspace_id=workspace.id,
            root_node_ids=orphan_ids,
        )


def _children_from_seeds(
    *,
    workspace: ContextWorkspace,
    seeds: tuple[ContextNodeSeed, ...],
    node_repository: ContextNodeRepository,
    preserve_existing_state: bool = True,
    preserve_existing_dynamic_roots: bool = False,
) -> tuple[ContextNode, ...]:
    children: list[ContextNode] = []
    for seed in seeds:
        node = ContextNode.from_seed(
            _seed_with_default_parent(seed),
            workspace_id=workspace.id,
        )
        existing = node_repository.get(
            workspace_id=workspace.id,
            node_id=node.id,
        )
        if existing is not None:
            node.created_at = existing.created_at
            if preserve_existing_state:
                node.apply_state(_state_for_existing_seed(node, existing))
                _preserve_existing_control_metadata(node, existing)
            if preserve_existing_dynamic_roots:
                _preserve_existing_dynamic_root_node(node, existing)
        children.append(node)
    return tuple(children)


def _seed_with_default_parent(seed: ContextNodeSeed) -> ContextNodeSeed:
    parent_id = seed.parent_id
    if parent_id is None:
        parent_id = root_nodes.default_parent_id_for_node_id(seed.node_id)
    if parent_id == seed.parent_id:
        return seed
    return ContextNodeSeed(
        node_id=seed.node_id,
        parent_id=parent_id,
        owner=seed.owner,
        kind=seed.kind,
        title=seed.title,
        summary=seed.summary,
        content=seed.content,
        state=seed.state,
        actions=seed.actions,
        owner_ref=dict(seed.owner_ref),
        estimate=seed.estimate,
        revision=seed.revision,
        freshness=seed.freshness,
        display_order=seed.display_order,
        metadata=dict(seed.metadata),
    )


def _state_for_existing_seed(
    node: ContextNode,
    existing: ContextNode,
) -> ContextNodeState:
    if node.id in {"context.priority", "context.tree_usage", "session.items.current"}:
        if node.revision != existing.revision:
            return node.state.with_updates(pinned=existing.state.pinned)
        return existing.state
    if node.owner == "session" and node.kind == "tool_interaction":
        if node.revision != existing.revision:
            return node.state.with_updates(
                pinned=existing.state.pinned,
                opened=existing.state.opened,
            )
        if _tool_interaction_owner_state_changed(node, existing):
            return node.state.with_updates(pinned=existing.state.pinned)
        return existing.state
    if node.owner == "tool" and node.kind in {
        "tool_bundle",
        "tool_bundle_group",
        "tool_function",
        "tool_cli_source",
    }:
        if node.kind == "tool_function":
            if _schema_enabled_was_set_by_action(existing):
                if node.revision != existing.revision:
                    return node.state.with_updates(
                        pinned=existing.state.pinned,
                        schema_enabled=existing.state.schema_enabled,
                    )
                return existing.state
            if existing.state.schema_enabled != node.state.schema_enabled:
                return node.state.with_updates(pinned=existing.state.pinned)
        if node.revision != existing.revision:
            return node.state.with_updates(pinned=existing.state.pinned)
        return existing.state
    if node.id == "tools.available" or node.id.endswith(".context_tree"):
        return node.state.with_updates(pinned=existing.state.pinned)
    return existing.state


def _record_schema_enabled_action(
    node: ContextNode,
    data: ContextActionInput,
) -> None:
    if data.action not in {
        ContextAction.ENABLE_TOOL_SCHEMA,
        ContextAction.DISABLE_TOOL_SCHEMA,
    }:
        return
    node.metadata[_SCHEMA_ENABLED_SOURCE_KEY] = _SCHEMA_ENABLED_SOURCE_ACTION
    node.metadata["schema_enabled_action"] = data.action.value
    if data.run_id is not None:
        node.metadata["schema_enabled_run_id"] = data.run_id


def _preserve_existing_control_metadata(
    node: ContextNode,
    existing: ContextNode,
) -> None:
    for key in (
        _SCHEMA_ENABLED_SOURCE_KEY,
        "schema_enabled_action",
        "schema_enabled_run_id",
    ):
        if key in existing.metadata:
            node.metadata[key] = existing.metadata[key]


def _schema_enabled_was_set_by_action(node: ContextNode) -> bool:
    return node.metadata.get(_SCHEMA_ENABLED_SOURCE_KEY) == _SCHEMA_ENABLED_SOURCE_ACTION


def _preserve_existing_dynamic_root_node(
    node: ContextNode,
    existing: ContextNode,
) -> None:
    if node.id != "work.plan":
        return
    node.summary = existing.summary
    node.content = existing.content
    node.owner_ref = dict(existing.owner_ref)
    node.estimate = existing.estimate
    node.revision = existing.revision
    node.freshness = existing.freshness
    node.metadata = dict(existing.metadata)


def _state_after_action(
    state: ContextNodeState,
    action: ContextAction,
) -> ContextNodeState:
    if action is ContextAction.EXPAND:
        return state.expand()
    if action is ContextAction.COLLAPSE:
        return state.collapse()
    if action is ContextAction.PIN:
        return state.with_updates(pinned=True)
    if action is ContextAction.UNPIN:
        return state.with_updates(pinned=False)
    if action is ContextAction.ENABLE_TOOL_SCHEMA:
        return state.with_updates(schema_enabled=True)
    if action is ContextAction.DISABLE_TOOL_SCHEMA:
        return state.with_updates(schema_enabled=False)
    return state.with_updates(loaded=True)


def _tool_interaction_owner_state_changed(
    node: ContextNode,
    existing: ContextNode,
) -> bool:
    for key in (
        "frontier",
        "consumed",
        "collapsed_by_default",
        "opened_by_default",
    ):
        if _metadata_bool(node.metadata.get(key)) != _metadata_bool(
            existing.metadata.get(key),
        ):
            return True
    for key in ("lifecycle_status", "content_digest"):
        if str(node.metadata.get(key) or "") != str(existing.metadata.get(key) or ""):
            return True
    return False


def _metadata_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


__all__ = [
    "ContextRenderService",
    "ContextTreeService",
    "ContextWorkspaceService",
]
