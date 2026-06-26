from __future__ import annotations

from crxzipple.modules.context_workspace.application.context_tree_maintenance import (
    ensure_default_root_nodes,
    load_owner_children,
    prune_orphan_nodes,
    refresh_owner_children,
)
from crxzipple.modules.context_workspace.application.models import (
    EnsureContextWorkspaceInput,
)
from crxzipple.modules.context_workspace.application.ports import ContextOwnerRegistry
from crxzipple.modules.context_workspace.domain import (
    ContextNode,
    ContextNodeRepository,
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
