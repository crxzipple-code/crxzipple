from __future__ import annotations

from crxzipple.modules.context_workspace.domain import (
    ContextNode,
    ContextRequestRenderSnapshot,
    ContextSnapshot,
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

    def delete_subtrees(
        self,
        *,
        workspace_id: str,
        root_node_ids: tuple[str, ...],
    ) -> None:
        root_ids = {
            node_id.strip()
            for node_id in root_node_ids
            if isinstance(node_id, str) and node_id.strip()
        }
        if not root_ids:
            return
        node_ids = set(root_ids)
        changed = True
        while changed:
            changed = False
            for (item_workspace_id, item_node_id), item in self._items.items():
                if item_workspace_id != workspace_id:
                    continue
                if item_node_id in node_ids:
                    continue
                if item.parent_id in node_ids:
                    node_ids.add(item_node_id)
                    changed = True
        for node_id in node_ids:
            self._items.pop((workspace_id, node_id), None)

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

    def list_enabled_tool_schema_nodes(
        self,
        workspace_id: str,
    ) -> tuple[ContextNode, ...]:
        return tuple(
            sorted(
                (
                    item
                    for key, item in self._items.items()
                    if key[0] == workspace_id
                    and item.owner == "tool"
                    and item.kind == "tool_function"
                    and item.state.schema_enabled
                ),
                key=lambda item: (item.display_order, item.id),
            ),
        )

    def list_tool_nodes_by_kind(
        self,
        workspace_id: str,
        *,
        kinds: tuple[str, ...],
    ) -> tuple[ContextNode, ...]:
        wanted = frozenset(kind for kind in kinds if kind)
        if not wanted:
            return ()
        return tuple(
            sorted(
                (
                    item
                    for key, item in self._items.items()
                    if key[0] == workspace_id
                    and item.owner == "tool"
                    and item.kind in wanted
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


class InMemoryContextSnapshotRepository:
    def __init__(self) -> None:
        self._items: dict[str, ContextSnapshot] = {}

    def add(self, snapshot: ContextSnapshot) -> None:
        self._items[snapshot.id] = snapshot

    def get(self, snapshot_id: str) -> ContextSnapshot | None:
        return self._items.get(snapshot_id)

    def get_by_run(self, run_id: str) -> ContextSnapshot | None:
        normalized = run_id.strip()
        items = [
            item
            for item in self._items.values()
            if item.run_id == normalized
        ]
        if not items:
            return None
        return sorted(
            items,
            key=lambda item: (item.created_at, item.id),
            reverse=True,
        )[0]

    def list_recent(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[ContextSnapshot, ...]:
        items = sorted(
            self._items.values(),
            key=lambda item: (item.created_at, item.id),
            reverse=True,
        )
        return tuple(items[max(0, offset) : max(0, offset) + max(1, limit)])


class InMemoryContextRequestRenderSnapshotRepository:
    def __init__(self) -> None:
        self._items: dict[str, ContextRequestRenderSnapshot] = {}

    def add(self, snapshot: ContextRequestRenderSnapshot) -> None:
        self._items[snapshot.id] = snapshot

    def get(self, snapshot_id: str) -> ContextRequestRenderSnapshot | None:
        return self._items.get(snapshot_id)

    def get_by_run(self, run_id: str) -> ContextRequestRenderSnapshot | None:
        normalized = run_id.strip()
        items = [
            item
            for item in self._items.values()
            if item.run_id == normalized
        ]
        if not items:
            return None
        return sorted(
            items,
            key=lambda item: (item.created_at, item.id),
            reverse=True,
        )[0]

    def list_recent(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[ContextRequestRenderSnapshot, ...]:
        items = sorted(
            self._items.values(),
            key=lambda item: (item.created_at, item.id),
            reverse=True,
        )
        return tuple(items[max(0, offset) : max(0, offset) + max(1, limit)])


__all__ = [
    "InMemoryContextNodeRepository",
    "InMemoryContextOperationRepository",
    "InMemoryContextRequestRenderSnapshotRepository",
    "InMemoryContextSnapshotRepository",
    "InMemoryContextWorkspaceRepository",
]
