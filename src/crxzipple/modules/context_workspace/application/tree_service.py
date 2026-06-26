from __future__ import annotations

from crxzipple.modules.context_workspace.application.context_tool_surface_projection import (
    tool_function_name,
)
from crxzipple.modules.context_workspace.application.context_tree_actions import (
    ContextTreeActionService,
)
from crxzipple.modules.context_workspace.application.context_tree_maintenance import (
    ensure_default_root_nodes,
    load_owner_children,
    refresh_owner_children,
)
from crxzipple.modules.context_workspace.application.models import (
    ContextActionInput,
    ContextActionResult,
    ContextNodeUpsertInput,
    ContextNodeUpsertResult,
    ContextTreeView,
)
from crxzipple.modules.context_workspace.application.ports import ContextOwnerRegistry
from crxzipple.modules.context_workspace.application.rendering import aggregate_estimate
from crxzipple.modules.context_workspace.domain import (
    ContextNode,
    ContextNodeRepository,
    ContextOperationRepository,
    ContextWorkspace,
    ContextWorkspaceNotFoundError,
    ContextWorkspaceRepository,
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
