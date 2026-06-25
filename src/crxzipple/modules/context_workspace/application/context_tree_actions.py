from __future__ import annotations

from uuid import uuid4

from crxzipple.modules.context_workspace.application.context_tree_maintenance import (
    children_from_seeds,
    load_owner_children,
    record_schema_enabled_action,
    state_after_action,
)
from crxzipple.modules.context_workspace.application.models import (
    ContextActionInput,
    ContextActionResult,
    ContextNodeUpsertInput,
    ContextNodeUpsertResult,
)
from crxzipple.modules.context_workspace.application.ports import ContextOwnerRegistry
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextActionNotAllowedError,
    ContextNodeNotFoundError,
    ContextNodeRepository,
    ContextOperationRepository,
    ContextTreeOperation,
    ContextWorkspace,
    ContextWorkspaceNotFoundError,
    ContextWorkspaceRepository,
)


class ContextTreeActionService:
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
        node.apply_state(state_after_action(node.state, data.action))
        record_schema_enabled_action(node, data)
        if data.action is ContextAction.EXPAND:
            load_owner_children(
                workspace=workspace,
                node=node,
                node_repository=self._nodes,
                owner_registry=self._owner_registry,
            )
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
        nodes = children_from_seeds(
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


__all__ = ["ContextTreeActionService"]
