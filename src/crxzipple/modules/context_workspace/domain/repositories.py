from __future__ import annotations

from typing import Protocol

from crxzipple.modules.context_workspace.domain.entities import (
    ContextNode,
    ContextRenderSnapshot,
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

    def get(self, *, workspace_id: str, node_id: str) -> ContextNode | None: ...

    def list_for_workspace(self, workspace_id: str) -> tuple[ContextNode, ...]: ...


class ContextOperationRepository(Protocol):
    def add(self, operation: ContextTreeOperation) -> None: ...

    def list_for_workspace(
        self,
        workspace_id: str,
        *,
        limit: int | None = None,
    ) -> tuple[ContextTreeOperation, ...]: ...


class ContextRenderSnapshotRepository(Protocol):
    def add(self, snapshot: ContextRenderSnapshot) -> None: ...

    def get(self, snapshot_id: str) -> ContextRenderSnapshot | None: ...

    def get_by_run(self, run_id: str) -> ContextRenderSnapshot | None: ...

    def list_recent(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[ContextRenderSnapshot, ...]: ...


__all__ = [
    "ContextNodeRepository",
    "ContextOperationRepository",
    "ContextRenderSnapshotRepository",
    "ContextWorkspaceRepository",
]
