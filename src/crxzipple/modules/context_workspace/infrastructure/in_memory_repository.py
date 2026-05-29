from __future__ import annotations

from crxzipple.modules.context_workspace.domain import (
    ContextNode,
    ContextRenderSnapshot,
    ContextTreeOperation,
    ContextWorkspace,
)


class InMemoryContextWorkspaceRepository:
    def __init__(self) -> None:
        self._items: dict[str, ContextWorkspace] = {}

    def add(self, workspace: ContextWorkspace) -> None:
        self._items[workspace.id] = workspace

    def save(self, workspace: ContextWorkspace) -> None:
        self._items[workspace.id] = workspace

    def get(self, workspace_id: str) -> ContextWorkspace | None:
        return self._items.get(workspace_id)

    def get_by_session(self, session_key: str) -> ContextWorkspace | None:
        normalized = session_key.strip()
        for item in self._items.values():
            if item.session_key == normalized:
                return item
        return None

    def list_recent(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[ContextWorkspace, ...]:
        items = sorted(
            self._items.values(),
            key=lambda item: (item.updated_at, item.id),
            reverse=True,
        )
        return tuple(items[max(0, offset) : max(0, offset) + max(1, limit)])


class InMemoryContextNodeRepository:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], ContextNode] = {}

    def save(self, node: ContextNode) -> None:
        self._items[(node.workspace_id, node.id)] = node

    def save_many(self, nodes: tuple[ContextNode, ...]) -> None:
        for node in nodes:
            self.save(node)

    def get(self, *, workspace_id: str, node_id: str) -> ContextNode | None:
        return self._items.get((workspace_id, node_id))

    def list_for_workspace(self, workspace_id: str) -> tuple[ContextNode, ...]:
        return tuple(
            sorted(
                (
                    item
                    for key, item in self._items.items()
                    if key[0] == workspace_id
                ),
                key=lambda item: (item.display_order, item.id),
            ),
        )


class InMemoryContextOperationRepository:
    def __init__(self) -> None:
        self._items: list[ContextTreeOperation] = []

    def add(self, operation: ContextTreeOperation) -> None:
        self._items.append(operation)

    def list_for_workspace(
        self,
        workspace_id: str,
        *,
        limit: int | None = None,
    ) -> tuple[ContextTreeOperation, ...]:
        items = [
            item for item in self._items if item.workspace_id == workspace_id
        ]
        items = sorted(items, key=lambda item: (item.created_at, item.id))
        if limit is not None and limit > 0:
            items = items[-limit:]
        return tuple(items)


class InMemoryContextRenderSnapshotRepository:
    def __init__(self) -> None:
        self._items: dict[str, ContextRenderSnapshot] = {}

    def add(self, snapshot: ContextRenderSnapshot) -> None:
        self._items[snapshot.id] = snapshot

    def get(self, snapshot_id: str) -> ContextRenderSnapshot | None:
        return self._items.get(snapshot_id)

    def get_by_run(self, run_id: str) -> ContextRenderSnapshot | None:
        normalized = run_id.strip()
        for item in self._items.values():
            if item.run_id == normalized:
                return item
        return None

    def list_recent(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[ContextRenderSnapshot, ...]:
        items = sorted(
            self._items.values(),
            key=lambda item: (item.created_at, item.id),
            reverse=True,
        )
        return tuple(items[max(0, offset) : max(0, offset) + max(1, limit)])


__all__ = [
    "InMemoryContextNodeRepository",
    "InMemoryContextOperationRepository",
    "InMemoryContextRenderSnapshotRepository",
    "InMemoryContextWorkspaceRepository",
]
