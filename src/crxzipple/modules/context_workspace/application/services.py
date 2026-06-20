from __future__ import annotations

from typing import Protocol
from uuid import uuid4

from crxzipple.modules.context_workspace.application import root_nodes
from crxzipple.modules.context_workspace.application.models import (
    BuildContextControlSliceInput,
    BuildContextObservationSliceInput,
    ContextActionInput,
    ContextActionResult,
    ContextControlRef,
    ContextControlReport,
    ContextControlSlice,
    ContextNodeUpsertInput,
    ContextNodeUpsertResult,
    ContextSlice,
    ContextSliceItem,
    ContextSliceReport,
    ContextSliceToolRef,
    ContextTreeView,
    EnsureContextWorkspaceInput,
    RecordContextSnapshotInput,
    ContextDebugDeltaInput,
    ContextDebugDeltaResult,
    ContextObservationRenderInput,
    ContextObservationRenderResult,
    RecordRequestRenderSnapshotInput,
)
from crxzipple.modules.context_workspace.application.ports import (
    ContextChildrenRequest,
    ContextOwnerRegistry,
)
from crxzipple.modules.context_workspace.application.rendering import (
    ContextTreeRenderPipeline,
    aggregate_estimate,
    snapshot_metadata_defaults,
)
from crxzipple.modules.context_workspace.application.rendering.xml_renderer import (
    tree_snapshot_visible_nodes,
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
    ContextSnapshot,
    ContextSnapshotNotFoundError,
    ContextSnapshotRepository,
    ContextRequestRenderSnapshot,
    ContextRequestRenderSnapshotRepository,
    ContextTreeOperation,
    ContextWorkspace,
    ContextWorkspaceNotFoundError,
    ContextWorkspaceRepository,
    ContextWorkspaceValidationError,
)


_SCHEMA_ENABLED_SOURCE_KEY = "schema_enabled_source"
_SCHEMA_ENABLED_SOURCE_ACTION = "context_tree_action"
_HANDLE_ONLY_OWNERS = frozenset(
    {
        "tool",
        "skills",
        "memory",
        "artifacts",
        "workspace",
        "agent",
    },
)
_EMBEDDED_CONTENT_OWNERS = frozenset(
    {
        "context_workspace",
        "llm",
        "orchestration",
        "runtime",
    },
)


class SessionItemResolver(Protocol):
    def get_item(self, item_id: str) -> object:
        ...


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
        _ensure_default_root_nodes(
            workspace=workspace,
            node_repository=self._nodes,
        )
        return self._nodes.get(workspace_id=workspace.id, node_id=node_id)

    def list_enabled_tool_schema_names(self, session_key: str) -> tuple[str, ...]:
        workspace = self._require_workspace(session_key)
        names: list[str] = []
        seen: set[str] = set()
        for node in self._nodes.list_enabled_tool_schema_nodes(workspace.id):
            name = _tool_function_name(node)
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
        audience = _normalize_slice_audience(audience)
        workspace = self._require_workspace(session_key)
        read_only = request_metadata.get("read_only") is True
        if not read_only:
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
        visible_nodes = _slice_visible_nodes(nodes, audience=audience)
        included_nodes = _included_nodes_for_slice(
            nodes=nodes,
            visible_nodes=visible_nodes,
            audience=audience,
            request_metadata=request_metadata,
        )
        resolved_items: list[ContextSliceItem] = []
        unresolved_refs: list[dict[str, object]] = []
        session_item_max_chars = _metadata_positive_int(
            request_metadata.get("session_item_max_chars"),
        )
        for node in included_nodes:
            item, unresolved_ref = _context_slice_item(
                node,
                session_item_resolver=self._session_item_resolver,
                session_item_max_chars=session_item_max_chars,
            )
            resolved_items.append(item)
            if unresolved_ref is not None:
                unresolved_refs.append(unresolved_ref)
        protocol_items, protocol_unresolved_refs = _protocol_required_slice_items(
            request_metadata.get("protocol_required_refs"),
            existing_session_item_ids=_included_session_item_ids(resolved_items),
            session_item_resolver=self._session_item_resolver,
        )
        resolved_items.extend(protocol_items)
        unresolved_refs.extend(protocol_unresolved_refs)
        requested_tool_schema_names = _metadata_string_set(
            request_metadata.get("requested_tool_schema_names"),
        )
        included_node_ids = {node.id for node in included_nodes}
        active_tools = tuple(
            tool_ref
            for node in nodes
            for tool_ref in (
                _context_slice_tool_ref(
                    node,
                    requested_tool_schema_names=requested_tool_schema_names,
                ),
            )
            if tool_ref is not None and _include_active_tools(audience)
        )
        omitted_node_ids = tuple(
            node.id for node in nodes if node.id not in included_node_ids
        )
        collapsed_refs = tuple(
            _collapsed_ref(node)
            for node in visible_nodes
            if node.state.collapsed
        )
        archived_refs = tuple(
            _archived_ref(node)
            for node in nodes
            if node.state.archived
        )
        redacted_refs: tuple[dict[str, object], ...] = ()
        report = ContextSliceReport(
            included_node_ids=tuple(node.id for node in included_nodes),
            omitted_node_ids=omitted_node_ids,
            archived_refs=archived_refs,
            collapsed_refs=collapsed_refs,
            redacted_refs=redacted_refs,
            unresolved_refs=tuple(unresolved_refs),
            budget=aggregate_estimate(included_nodes).to_payload(),
            loss={
                "omitted_node_count": len(omitted_node_ids),
                "archived_ref_count": len(archived_refs),
                "collapsed_ref_count": len(collapsed_refs),
                "redacted_ref_count": len(redacted_refs),
                "unresolved_ref_count": len(unresolved_refs),
            },
            metadata={
                "audience": audience,
                "provider_profile": provider_profile or "",
                "visible_node_count": len(visible_nodes),
                "active_tool_count": len(active_tools),
                "read_only": read_only,
                **request_metadata,
            },
        )
        slice_id = f"ctxslice_{uuid4().hex}"
        return ContextSlice(
            slice_id=slice_id,
            session_key=workspace.session_key,
            run_id=run_id,
            audience=audience,
            tree_revision=workspace.active_revision,
            items=tuple(resolved_items),
            active_tools=active_tools,
            report=report,
            metadata={
                "slice_id": slice_id,
                "audience": audience,
                "provider_profile": provider_profile or "",
                "workspace_id": workspace.id,
                "read_only": read_only,
                **request_metadata,
            },
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
        audience = _normalize_slice_audience(audience)
        workspace = self._require_workspace(session_key)
        read_only = request_metadata.get("read_only") is True
        if not read_only:
            _ensure_default_root_nodes(
                workspace=workspace,
                node_repository=self._nodes,
            )
        nodes = self._nodes.list_for_workspace(workspace.id)
        visible_nodes = _slice_visible_nodes(nodes, audience=audience)
        selected_nodes = _included_nodes_for_slice(
            nodes=nodes,
            visible_nodes=visible_nodes,
            audience=audience,
            request_metadata=request_metadata,
        )
        selected_node_ids = {node.id for node in selected_nodes}
        requested_tool_schema_names = _metadata_string_set(
            request_metadata.get("requested_tool_schema_names"),
        )
        active_tools = tuple(
            tool_ref
            for node in nodes
            for tool_ref in (
                _context_slice_tool_ref(
                    node,
                    requested_tool_schema_names=requested_tool_schema_names,
                ),
            )
            if tool_ref is not None and _include_active_tools(audience)
        )
        collapsed_refs = tuple(
            _collapsed_ref(node)
            for node in visible_nodes
            if node.state.collapsed
        )
        archived_refs = tuple(
            _archived_ref(node)
            for node in nodes
            if node.state.archived
        )
        protocol_required_refs = tuple(
            dict(item)
            for item in _metadata_dict_list(
                request_metadata.get("protocol_required_refs"),
            )
        )
        selected_refs = _merge_control_refs_with_protocol_required(
            selected_nodes=selected_nodes,
            protocol_required_refs=protocol_required_refs,
        )
        selected_ref_node_ids = tuple(item.node_id for item in selected_refs)
        omitted_node_ids = tuple(
            node.id for node in nodes if node.id not in selected_node_ids
        )
        report = ContextControlReport(
            selected_node_ids=selected_ref_node_ids,
            omitted_node_ids=omitted_node_ids,
            collapsed_refs=collapsed_refs,
            archived_refs=archived_refs,
            protocol_required_refs=protocol_required_refs,
            metadata={
                "audience": audience,
                "provider_profile": provider_profile or "",
                "visible_node_count": len(visible_nodes),
                "active_tool_count": len(active_tools),
                "tree_scan_performed": True,
                "read_only": read_only,
                "tree_backed_selected_node_count": len(selected_nodes),
                "protocol_synthetic_ref_count": max(
                    0,
                    len(selected_refs) - len(selected_nodes),
                ),
                **request_metadata,
            },
        )
        slice_id = f"ctxctrl_{uuid4().hex}"
        return ContextControlSlice(
            slice_id=slice_id,
            session_key=workspace.session_key,
            run_id=run_id,
            audience=audience,
            tree_revision=workspace.active_revision,
            selected_refs=selected_refs,
            active_tools=active_tools,
            report=report,
            metadata={
                "slice_id": slice_id,
                "audience": audience,
                "provider_profile": provider_profile or "",
                "workspace_id": workspace.id,
                "tree_scan_performed": True,
                "read_only": read_only,
                **request_metadata,
            },
        )

    def _require_workspace(self, session_key: str) -> ContextWorkspace:
        workspace = self._workspaces.get_by_session(session_key)
        if workspace is None:
            raise ContextWorkspaceNotFoundError(
                f"Context workspace for session '{session_key}' was not found.",
            )
        return workspace


def _preloads_children(node: ContextNode) -> bool:
    if node.owner == "tool" and node.id == "tools.available":
        return True
    if node.owner == "workspace" and node.id == "workspace.resources":
        return True
    if node.owner == "session" and node.id in {
        "session.current",
        "session.instance.active",
        "session.segments.active",
        "session.segment.active",
    }:
        return True
    return False


def _normalize_slice_audience(value: str) -> str:
    normalized = str(value or "").strip() or "llm_request"
    allowed = {
        "llm_request",
        "user_timeline",
        "trace_timeline",
        "debug_tree",
        "operations_projection",
    }
    if normalized not in allowed:
        raise ContextWorkspaceValidationError(
            f"Unsupported context observation slice audience: {normalized}",
        )
    return normalized


def _control_ref_from_session_ref(
    ref: dict[str, object],
) -> ContextControlRef | None:
    item_id = _session_item_id_from_protocol_ref(ref)
    if item_id is None:
        return None
    owner_ref = dict(ref)
    owner_ref.setdefault("session_item_id", item_id)
    owner_ref.setdefault("item_id", item_id)
    owner_ref.setdefault("owner_id", item_id)
    node_id = _metadata_text(ref.get("node_id")) or f"session.item.{item_id}"
    kind = _metadata_text(ref.get("owner_kind")) or _metadata_text(ref.get("kind"))
    if kind is None or kind in {"message", "tool_result"}:
        kind = "session_item"
    role = _metadata_text(ref.get("role"))
    title = f"{role} {item_id}" if role else item_id
    return ContextControlRef(
        node_id=node_id,
        owner="session",
        kind=kind,
        title=title,
        owner_ref=owner_ref,
        metadata={
            "status": _metadata_text(ref.get("status")) or "known",
            "protocol_required": True,
            "tree_backed": False,
        },
    )


def _merge_control_refs_with_protocol_required(
    *,
    selected_nodes: tuple[ContextNode, ...],
    protocol_required_refs: tuple[dict[str, object], ...],
) -> tuple[ContextControlRef, ...]:
    selected_refs = [_context_control_ref(node) for node in selected_nodes]
    selected_session_item_ids = {
        text
        for item in selected_refs
        for text in (
            _metadata_text(item.owner_ref.get("session_item_id")),
            _metadata_text(item.owner_ref.get("item_id")),
            _metadata_text(item.owner_ref.get("owner_id")),
        )
        if text is not None
    }
    selected_node_ids = {item.node_id for item in selected_refs}
    for ref in protocol_required_refs:
        control_ref = _control_ref_from_session_ref(ref)
        if control_ref is None:
            continue
        ref_session_item_id = (
            _metadata_text(control_ref.owner_ref.get("session_item_id"))
            or _metadata_text(control_ref.owner_ref.get("item_id"))
            or _metadata_text(control_ref.owner_ref.get("owner_id"))
        )
        if control_ref.node_id in selected_node_ids:
            continue
        if ref_session_item_id is not None and ref_session_item_id in selected_session_item_ids:
            continue
        selected_refs.append(control_ref)
        selected_node_ids.add(control_ref.node_id)
        if ref_session_item_id is not None:
            selected_session_item_ids.add(ref_session_item_id)
    return tuple(selected_refs)


def _collapsed_ref(node: ContextNode) -> dict[str, object]:
    return {
        "node_id": node.id,
        "owner": node.owner,
        "kind": node.kind,
        "title": node.title,
    }


def _archived_ref(node: ContextNode) -> dict[str, object]:
    ref: dict[str, object] = {
        "node_id": node.id,
        "owner": node.owner,
        "kind": node.kind,
        "title": node.title,
        "reason": _metadata_text(node.metadata.get("archived_reason"))
        or _metadata_text(node.owner_ref.get("archived_reason"))
        or "archived",
    }
    for key in (
        "session_key",
        "session_id",
        "session_item_id",
        "sequence_no",
        "summary_item_id",
        "archived_by_compaction_run_id",
        "compacted_segment_id",
        "archived_through_item_sequence_no",
    ):
        value = node.owner_ref.get(key)
        if value not in (None, "", {}, []):
            ref[key] = value
    return ref


def _slice_visible_nodes(
    nodes: tuple[ContextNode, ...],
    *,
    audience: str,
) -> tuple[ContextNode, ...]:
    if audience == "debug_tree":
        return nodes
    return tuple(
        node
        for node in tree_snapshot_visible_nodes(nodes)
        if not node.state.archived
    )


def _include_active_tools(audience: str) -> bool:
    return audience in {"llm_request", "trace_timeline", "operations_projection"}


def _node_included_in_slice(node: ContextNode, *, audience: str) -> bool:
    if audience == "debug_tree":
        return True
    if audience == "user_timeline":
        return _node_included_in_user_timeline_slice(node)
    if audience == "trace_timeline":
        return _node_included_in_trace_timeline_slice(node)
    if audience == "operations_projection":
        return _node_included_in_operations_projection_slice(node)
    if audience == "llm_request":
        return _node_included_in_llm_request_slice(node)
    return False


def _included_nodes_for_slice(
    *,
    nodes: tuple[ContextNode, ...],
    visible_nodes: tuple[ContextNode, ...],
    audience: str,
    request_metadata: dict[str, object],
) -> tuple[ContextNode, ...]:
    included: list[ContextNode] = [
        node
        for node in visible_nodes
        if _node_included_in_slice(node, audience=audience)
    ]
    if audience != "llm_request":
        return tuple(included)
    protocol_required_ids = _protocol_required_ref_ids(
        request_metadata.get("protocol_required_refs"),
    )
    included_ids = {node.id for node in included}
    for node in nodes:
        if node.id in included_ids or node.state.archived:
            continue
        if node.owner == "session" and (
            _node_protocol_required(node)
            or _node_matches_protocol_required_ref(node, protocol_required_ids)
        ):
            included.append(node)
            included_ids.add(node.id)
    return tuple(included)


def _protocol_required_ref_ids(value: object) -> frozenset[str]:
    if not isinstance(value, (list, tuple)):
        return frozenset()
    ids: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        for key in ("node_id", "owner_id", "item_id", "session_item_id"):
            text = _metadata_text(item.get(key))
            if text is not None:
                ids.add(text)
    return frozenset(ids)


def _included_session_item_ids(items: list[ContextSliceItem]) -> frozenset[str]:
    ids: set[str] = set()
    for item in items:
        text = _metadata_text(item.owner_ref.get("session_item_id"))
        if text is not None:
            ids.add(text)
    return frozenset(ids)


def _protocol_required_slice_items(
    value: object,
    *,
    existing_session_item_ids: frozenset[str],
    session_item_resolver: SessionItemResolver | None,
) -> tuple[list[ContextSliceItem], list[dict[str, object]]]:
    if not isinstance(value, (list, tuple)):
        return [], []
    items: list[ContextSliceItem] = []
    unresolved: list[dict[str, object]] = []
    for ref in value:
        if not isinstance(ref, dict):
            continue
        session_item_id = _session_item_id_from_protocol_ref(ref)
        if session_item_id is None or session_item_id in existing_session_item_ids:
            continue
        item, unresolved_ref = _protocol_required_slice_item(
            ref,
            session_item_id=session_item_id,
            session_item_resolver=session_item_resolver,
        )
        if item is not None:
            items.append(item)
        if unresolved_ref is not None:
            unresolved.append(unresolved_ref)
    return items, unresolved


def _session_item_id_from_protocol_ref(ref: dict[str, object]) -> str | None:
    explicit = (
        _metadata_text(ref.get("session_item_id"))
        or _metadata_text(ref.get("item_id"))
        or _metadata_text(ref.get("call_session_item_id"))
        or _metadata_text(ref.get("result_session_item_id"))
    )
    if explicit is not None:
        return explicit
    if _metadata_text(ref.get("source_owner_kind")) == "session_item":
        source_owner_id = _metadata_text(ref.get("source_owner_id"))
        if source_owner_id is not None:
            return source_owner_id
    if _metadata_text(ref.get("owner_kind")) == "session_item":
        return _metadata_text(ref.get("owner_id"))
    return None


def _protocol_required_slice_item(
    ref: dict[str, object],
    *,
    session_item_id: str,
    session_item_resolver: SessionItemResolver | None,
) -> tuple[ContextSliceItem | None, dict[str, object] | None]:
    if session_item_resolver is None:
        return None, {
            "owner": "session",
            "kind": _metadata_text(ref.get("kind")) or "session_item",
            "owner_ref": dict(ref),
            "reason": "session_item_resolver_unavailable",
        }
    try:
        session_item = session_item_resolver.get_item(session_item_id)
    except Exception as exc:  # owner query errors stay in loss report only
        return None, {
            "owner": "session",
            "kind": _metadata_text(ref.get("kind")) or "session_item",
            "owner_ref": dict(ref),
            "reason": "session_item_resolve_failed",
            "error_type": type(exc).__name__,
        }
    owner_ref = {**dict(ref), **_session_item_owner_ref(session_item)}
    owner_ref["session_item_id"] = session_item_id
    raw_kind = _metadata_text(ref.get("kind"))
    if raw_kind == "tool_call":
        kind = "runtime_assistant_tool_call"
    elif raw_kind == "tool_result":
        kind = "runtime_tool_result"
    else:
        kind = "session_item"
    text = _session_item_model_text(session_item) or ""
    content = _session_item_model_content(session_item)
    sequence_no = owner_ref.get("sequence_no")
    title = (
        f"{sequence_no}. {owner_ref.get('role')}"
        if sequence_no not in (None, "")
        else _metadata_text(ref.get("title")) or kind
    )
    return (
        ContextSliceItem(
            item_id=_metadata_text(ref.get("node_id"))
            or f"protocol.session_item.{session_item_id}",
            node_id=_metadata_text(ref.get("node_id")),
            section="tool_results" if kind == "runtime_tool_result" else "history",
            owner="session",
            kind=kind,
            title=str(title),
            summary=_metadata_text(ref.get("summary")) or "",
            text=text,
            content=content,
            owner_ref=owner_ref,
            metadata={
                "summary_mode": "full",
                "status": "available",
                "render_priority": 0,
                "render_reason": "protocol_required",
                "freshness": "live",
                "resolved_from_owner": True,
                "owner_resolution": "owner_resolved",
                "protocol_required": True,
            },
        ),
        None,
    )


def _node_matches_protocol_required_ref(
    node: ContextNode,
    protocol_required_ids: frozenset[str],
) -> bool:
    if not protocol_required_ids:
        return False
    if node.id in protocol_required_ids:
        return True
    for key in ("owner_id", "item_id", "session_item_id"):
        text = _metadata_text(node.owner_ref.get(key))
        if text is not None and text in protocol_required_ids:
            return True
    return False


def _node_included_in_llm_request_slice(node: ContextNode) -> bool:
    if node.state.included_in_next_slice:
        return True
    if node.state.pinned or node.state.opened:
        return True
    if node.owner == "session" and node.kind in {
        "runtime_tool_result",
        "runtime_assistant_tool_call",
        "tool_interaction",
    }:
        return _node_protocol_required(node)
    if node.owner == "session" and node.kind in {
        "runtime_assistant_message",
        "runtime_assistant_progress",
        "runtime_session_message",
        "session_segment",
        "session_item",
        "session_item_range",
    }:
        if node.kind == "session_segment":
            return (
                _metadata_text(node.owner_ref.get("segment_kind")) == "compacted"
                and _metadata_bool(node.owner_ref.get("has_summary"))
            )
        return True
    if node.owner == "orchestration" and node.kind == "run_goal":
        return True
    if node.owner in {"skills", "memory", "artifacts", "workspace"}:
        return node.state.pinned or node.state.opened or node.state.included_in_next_slice
    return False


def _node_included_in_user_timeline_slice(node: ContextNode) -> bool:
    if node.state.included_in_next_slice or node.state.pinned or node.state.opened:
        return True
    if node.owner != "session":
        return False
    return node.kind in {
        "session_turn",
        "session_step",
        "runtime_assistant_progress",
        "runtime_assistant_message",
        "runtime_session_message",
        "runtime_tool_run",
        "runtime_tool_result",
        "session_item",
        "session_item_range",
        "tool_interaction",
    }


def _node_included_in_trace_timeline_slice(node: ContextNode) -> bool:
    if node.state.included_in_next_slice or node.state.pinned or node.state.opened:
        return True
    if node.owner in {"session", "orchestration", "runtime", "agent"}:
        return True
    if node.owner == "tool":
        return node.kind in {"tool_function", "tool_group", "tool_source"}
    return False


def _node_included_in_operations_projection_slice(node: ContextNode) -> bool:
    if node.state.included_in_next_slice or node.state.pinned or node.state.opened:
        return True
    if node.owner in {"session", "orchestration", "runtime", "agent", "tool"}:
        return True
    return node.owner in {"skills", "memory", "artifacts", "workspace"} and (
        node.state.pinned or node.state.opened
    )


def _node_protocol_required(node: ContextNode) -> bool:
    if _metadata_bool(node.owner_ref.get("protocol_required")):
        return True
    if _metadata_bool(node.metadata.get("protocol_required")):
        return True
    return (
        _metadata_text(node.owner_ref.get("budget_class")) == "protocol_required"
        or _metadata_text(node.metadata.get("budget_class")) == "protocol_required"
    )


def _context_slice_item(
    node: ContextNode,
    *,
    session_item_resolver: SessionItemResolver | None = None,
    session_item_max_chars: int | None = None,
) -> tuple[ContextSliceItem, dict[str, object] | None]:
    text = node.content if _node_allows_embedded_content(node) else ""
    content: object | None = None
    owner_ref = dict(node.owner_ref)
    owner_resolution = _default_owner_resolution(node)
    metadata = {
        "summary_mode": node.state.summary_mode,
        "status": node.state.status,
        "render_priority": node.state.render_priority,
        "render_reason": node.state.render_reason,
        "freshness": node.freshness,
        "resolved_from_owner": False,
        "owner_resolution": owner_resolution,
    }
    unresolved_ref: dict[str, object] | None = None
    if node.owner == "session":
        (
            resolved_text,
            resolved_content,
            resolved_owner_ref,
            unresolved_ref,
        ) = _resolve_session_slice_item(
            node,
            session_item_resolver=session_item_resolver,
            max_chars=session_item_max_chars,
        )
        owner_ref.update(resolved_owner_ref)
        if resolved_content is not None:
            content = resolved_content
            metadata["resolved_from_owner"] = True
            metadata["owner_resolution"] = "owner_resolved"
        if resolved_text is not None:
            text = resolved_text
            metadata["resolved_from_owner"] = True
            metadata["owner_resolution"] = "owner_resolved"
        elif unresolved_ref is not None:
            metadata["owner_resolution"] = "owner_unresolved"
    item = ContextSliceItem(
        item_id=node.id,
        node_id=node.id,
        section=_slice_section_for_node(node),
        owner=node.owner,
        kind=node.kind,
        title=node.title,
        summary=node.summary,
        text=text,
        content=content,
        owner_ref=owner_ref,
        estimate=node.estimate,
        metadata=metadata,
    )
    return item, unresolved_ref


def _node_allows_embedded_content(node: ContextNode) -> bool:
    if node.owner == "session":
        return False
    if node.owner in _HANDLE_ONLY_OWNERS:
        return False
    return node.owner in _EMBEDDED_CONTENT_OWNERS


def _default_owner_resolution(node: ContextNode) -> str:
    if _node_allows_embedded_content(node):
        return "embedded"
    if node.owner == "session":
        return "owner_resolved"
    return "handle_only"


def _resolve_session_slice_item(
    node: ContextNode,
    *,
    session_item_resolver: SessionItemResolver | None,
    max_chars: int | None = None,
) -> tuple[str | None, object | None, dict[str, object], dict[str, object] | None]:
    session_item_id = _metadata_text(node.owner_ref.get("session_item_id"))
    if session_item_id is None:
        return None, None, {}, None
    if session_item_resolver is None:
        return None, None, {}, {
            "node_id": node.id,
            "owner": node.owner,
            "kind": node.kind,
            "owner_ref": dict(node.owner_ref),
            "reason": "session_item_resolver_unavailable",
        }
    try:
        item = session_item_resolver.get_item(session_item_id)
    except Exception as exc:  # owner query errors stay in loss report only
        return None, None, {}, {
            "node_id": node.id,
            "owner": node.owner,
            "kind": node.kind,
            "owner_ref": dict(node.owner_ref),
            "reason": "session_item_resolve_failed",
            "error_type": type(exc).__name__,
        }
    text = _session_item_model_text(item)
    content = _session_item_model_content(item)
    text, content = _truncate_session_projection(
        text,
        content,
        max_chars=max_chars,
    )
    owner_ref = _session_item_owner_ref(item)
    if text is None and content is None:
        return None, None, owner_ref, {
            "node_id": node.id,
            "owner": node.owner,
            "kind": node.kind,
            "owner_ref": dict(node.owner_ref),
            "reason": "session_item_has_no_model_content",
        }
    return text, content, owner_ref, None


def _truncate_session_projection(
    text: str | None,
    content: object | None,
    *,
    max_chars: int | None,
) -> tuple[str | None, object | None]:
    if max_chars is None or max_chars <= 0:
        return text, content
    if text is None or len(text) <= max_chars:
        return text, content
    truncated = text[-max_chars:]
    return truncated, [{"type": "text", "text": truncated}]


def _slice_section_for_node(node: ContextNode) -> str:
    if node.id in {"run.goal", "work.plan"} or node.id.startswith("task."):
        return "task"
    if node.owner == "runtime" or node.id.startswith("run."):
        return "runtime"
    if node.owner == "session":
        if node.kind in {"tool_interaction", "runtime_tool_result"}:
            return "tool_results"
        return "history"
    if node.owner == "skills":
        return "skills"
    if node.owner == "memory":
        return "memory"
    if node.owner == "artifacts":
        return "artifacts"
    if node.owner == "workspace":
        return "workspace"
    return "runtime"


def _context_slice_tool_ref(
    node: ContextNode,
    *,
    requested_tool_schema_names: frozenset[str] = frozenset(),
) -> ContextSliceToolRef | None:
    if node.owner != "tool" or node.kind != "tool_function":
        return None
    function_name = _tool_function_name(node)
    if not isinstance(function_name, str) or not function_name.strip():
        return None
    function_name = function_name.strip()
    if not (
        node.state.schema_enabled
        or node.state.included_in_next_tool_surface
        or function_name in requested_tool_schema_names
    ):
        return None
    source_id = _metadata_text(node.owner_ref.get("source_id")) or ""
    return ContextSliceToolRef(
        tool_ref_id=node.id,
        node_id=node.id,
        source_id=source_id,
        function_name=function_name,
        owner_ref=dict(node.owner_ref),
        metadata={
            "status": node.state.status,
            "render_priority": node.state.render_priority,
        },
    )


def _tool_function_name(node: ContextNode) -> str | None:
    for value in (
        node.owner_ref.get("tool_id"),
        node.owner_ref.get("function_id"),
        node.metadata.get("function_name"),
    ):
        text = _metadata_text(value)
        if text is not None:
            return text
    return None


def _context_control_ref(node: ContextNode) -> ContextControlRef:
    return ContextControlRef(
        node_id=node.id,
        owner=node.owner,
        kind=node.kind,
        title=node.title,
        owner_ref=dict(node.owner_ref),
        metadata={
            "status": node.state.status,
            "collapsed": node.state.collapsed,
            "pinned": node.state.pinned,
            "schema_enabled": node.state.schema_enabled,
            "included_in_next_tool_surface": (
                node.state.included_in_next_tool_surface
            ),
            "render_priority": node.state.render_priority,
            "revision": node.revision,
        },
    )


def _session_item_model_text(item: object) -> str | None:
    payload = getattr(item, "content_payload", None)
    if not isinstance(payload, dict):
        return None
    blocks = payload.get("blocks")
    if isinstance(blocks, list):
        lines = tuple(
            text
            for block in blocks
            for text in (_content_block_model_text(block),)
            if text is not None
        )
        if lines:
            return "\n".join(lines)
    content = payload.get("content")
    if isinstance(content, list):
        lines = tuple(
            text
            for block in content
            for text in (_content_block_model_text(block),)
            if text is not None
        )
        if lines:
            return "\n".join(lines)
    for key in ("text", "content", "summary"):
        value = _metadata_text(payload.get(key))
        if value is not None:
            return value
    return None


def _session_item_model_content(item: object) -> object | None:
    payload = getattr(item, "content_payload", None)
    if not isinstance(payload, dict):
        return None
    blocks = payload.get("blocks")
    if isinstance(blocks, list) and blocks:
        return [dict(block) if isinstance(block, dict) else block for block in blocks]
    content = payload.get("content")
    if isinstance(content, list) and content:
        return [dict(block) if isinstance(block, dict) else block for block in content]
    return None


def _session_item_owner_ref(item: object) -> dict[str, object]:
    payload = getattr(item, "content_payload", None)
    metadata = getattr(item, "metadata", None)
    role = _metadata_text(getattr(item, "role", None))
    owner_ref: dict[str, object] = {}
    item_id = _metadata_text(getattr(item, "id", None))
    session_id = _metadata_text(getattr(item, "session_id", None))
    sequence_no = getattr(item, "sequence_no", None)
    kind = _metadata_text(getattr(item, "kind", None))
    source_kind = _metadata_text(getattr(item, "source_kind", None))
    provider_item_type = _metadata_text(getattr(item, "provider_item_type", None))
    model_visible = getattr(item, "model_visible", None)
    if item_id is not None:
        owner_ref["session_item_id"] = item_id
    if session_id is not None:
        owner_ref["session_id"] = session_id
    if isinstance(sequence_no, int):
        owner_ref["sequence_no"] = sequence_no
    if kind is not None:
        owner_ref["kind"] = kind
    if role is not None:
        owner_ref["role"] = role
    if isinstance(model_visible, bool):
        owner_ref["model_visible"] = model_visible
    if source_kind is not None:
        owner_ref["source_kind"] = source_kind
    if provider_item_type is not None:
        owner_ref["provider_item_type"] = provider_item_type
    if not isinstance(payload, dict):
        payload = {}
    if not isinstance(metadata, dict):
        metadata = {}
    runtime_semantic_kind = _metadata_text(metadata.get("runtime_semantic_kind"))
    if runtime_semantic_kind is not None:
        owner_ref["runtime_semantic_kind"] = runtime_semantic_kind
    for key in ("tool_call_id", "tool_name", "tool_run_id", "llm_response_item_id"):
        value = _metadata_text(metadata.get(key)) or _metadata_text(payload.get(key))
        if value is not None:
            owner_ref[key] = value
    if isinstance(payload.get("arguments"), (dict, list, str, int, float, bool)):
        owner_ref["arguments"] = payload.get("arguments")
    call_id = _metadata_text(payload.get("call_id"))
    if call_id is not None and "tool_call_id" not in owner_ref:
        owner_ref["tool_call_id"] = call_id
    name = _metadata_text(payload.get("name"))
    if name is not None and "tool_name" not in owner_ref:
        owner_ref["tool_name"] = name
    return owner_ref


def _content_block_model_text(block: object) -> str | None:
    if not isinstance(block, dict):
        return None
    block_type = _metadata_text(block.get("type")) or "text"
    if block_type == "text":
        return _metadata_text(block.get("text"))
    if block_type in {"image", "image_ref"}:
        name = _metadata_text(block.get("name")) or _metadata_text(block.get("filename"))
        artifact_id = _metadata_text(block.get("artifact_id"))
        label = name or artifact_id or "image"
        return f"[image:{label}]"
    if block_type in {"file", "file_ref"}:
        name = _metadata_text(block.get("name")) or _metadata_text(block.get("filename"))
        artifact_id = _metadata_text(block.get("artifact_id"))
        label = name or artifact_id or "file"
        return f"[file:{label}]"
    return _metadata_text(block.get("text")) or f"[{block_type}]"


def _metadata_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _metadata_dict_list(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(dict(item) for item in value if isinstance(item, dict))


def _metadata_string_set(value: object) -> frozenset[str]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        return frozenset()
    return frozenset(
        text
        for item in value
        if isinstance(item, str) and (text := item.strip())
    )


def _metadata_positive_int(value: object) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _metadata_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


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
    preload_only: bool = False,
) -> None:
    nodes = node_repository.list_for_workspace(workspace.id)
    for node in nodes:
        if node.state.collapsed and not _preloads_children(node):
            continue
        if not _can_load_owner_children(node):
            continue
        _load_owner_children(
            workspace=workspace,
            node=node,
            node_repository=node_repository,
            owner_registry=owner_registry,
            workspace_nodes=nodes,
            recursive=True,
            preload_only=preload_only,
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
    workspace_nodes: tuple[ContextNode, ...] | None = None,
    recursive: bool = False,
    preload_only: bool = False,
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
    nodes_for_stale_check = (
        workspace_nodes
        if workspace_nodes is not None
        else node_repository.list_for_workspace(workspace.id)
    )
    stale_child_ids = tuple(
        child.id
        for child in nodes_for_stale_check
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
    if not recursive:
        return
    for child in children:
        if child.state.collapsed and not _preloads_children(child):
            continue
        if preload_only and not _preloads_children(child):
            continue
        _load_owner_children(
            workspace=workspace,
            node=child,
            node_repository=node_repository,
            owner_registry=owner_registry,
            recursive=True,
            preload_only=preload_only,
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
        if node.kind == "tool_function" and _is_internal_context_tool_function(node):
            return node.state.with_updates(pinned=existing.state.pinned)
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


def _is_internal_context_tool_function(node: ContextNode) -> bool:
    tool_id = _metadata_text(node.owner_ref.get("tool_id")) or _metadata_text(
        node.metadata.get("tool_id"),
    )
    if tool_id == "capability.search":
        return False
    if tool_id is not None and tool_id.startswith("context_tree."):
        return True
    source_id = _metadata_text(node.owner_ref.get("source_id")) or _metadata_text(
        node.metadata.get("source_id"),
    )
    return bool(source_id and source_id.endswith(".context_tree"))


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
    "ContextControlSliceService",
    "ContextSliceBuilderService",
    "ContextObservationSnapshotService",
    "ContextTreeService",
    "ContextWorkspaceService",
]
