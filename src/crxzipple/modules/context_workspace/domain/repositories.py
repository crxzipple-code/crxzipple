from __future__ import annotations

from typing import Protocol

from crxzipple.modules.context_workspace.domain.entities import (
    ContextNode,
    ContextRequestRenderSnapshot,
    ContextSnapshot,
    ContextTreeOperation,
    ContextWorkspace,
)


class ContextWorkspaceRepository(Protocol):
    def add(self, workspace: ContextWorkspace) -> None: ...

    def save(self, workspace: ContextWorkspace) -> None: ...

    def get(self, workspace_id: str) -> ContextWorkspace | None: ...

    def get_by_session(self, session_key: str) -> ContextWorkspace | None: ...

    def list_recent(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[ContextWorkspace, ...]: ...


class ContextNodeRepository(Protocol):
    def save(self, node: ContextNode) -> None: ...

    def save_many(self, nodes: tuple[ContextNode, ...]) -> None: ...

    def delete_subtrees(
        self,
        *,
        workspace_id: str,
        root_node_ids: tuple[str, ...],
    ) -> None: ...

    def get(self, *, workspace_id: str, node_id: str) -> ContextNode | None: ...

    def list_for_workspace(self, workspace_id: str) -> tuple[ContextNode, ...]: ...

    def list_enabled_tool_schema_nodes(
        self,
        workspace_id: str,
    ) -> tuple[ContextNode, ...]: ...

    def list_tool_nodes_by_kind(
        self,
        workspace_id: str,
        *,
        kinds: tuple[str, ...],
    ) -> tuple[ContextNode, ...]: ...


class ContextOperationRepository(Protocol):
    def add(self, operation: ContextTreeOperation) -> None: ...

    def list_for_workspace(
        self,
        workspace_id: str,
        *,
        limit: int | None = None,
    ) -> tuple[ContextTreeOperation, ...]: ...


class ContextSnapshotRepository(Protocol):
    def add(self, snapshot: ContextSnapshot) -> None: ...

    def get(self, snapshot_id: str) -> ContextSnapshot | None: ...

    def get_by_run(self, run_id: str) -> ContextSnapshot | None: ...

    def list_recent(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[ContextSnapshot, ...]: ...


class ContextRequestRenderSnapshotRepository(Protocol):
    def add(self, snapshot: ContextRequestRenderSnapshot) -> None: ...

    def get(self, snapshot_id: str) -> ContextRequestRenderSnapshot | None: ...

    def get_by_run(self, run_id: str) -> ContextRequestRenderSnapshot | None: ...

    def list_recent(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[ContextRequestRenderSnapshot, ...]: ...


__all__ = [
    "ContextNodeRepository",
    "ContextOperationRepository",
    "ContextRequestRenderSnapshotRepository",
    "ContextSnapshotRepository",
    "ContextWorkspaceRepository",
]
