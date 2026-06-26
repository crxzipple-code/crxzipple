from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from crxzipple.core.db import SessionFactory
from crxzipple.modules.context_workspace.domain import (
    ContextNode,
    ContextRequestRenderSnapshot,
    ContextSnapshot,
    ContextTreeOperation,
    ContextWorkspace,
)
from crxzipple.modules.context_workspace.infrastructure.persistence.models import (
    ContextNodeStateModel,
    ContextOperationModel,
    ContextRequestRenderSnapshotModel,
    ContextSnapshotModel,
    ContextWorkspaceModel,
)
from crxzipple.modules.context_workspace.infrastructure.persistence.repository_mappers import (
    apply_node,
    apply_request_render_snapshot,
    apply_snapshot,
    apply_workspace,
    node_from_model,
    node_model,
    operation_from_model,
    operation_model,
    request_render_snapshot_from_model,
    request_render_snapshot_model,
    snapshot_from_model,
    snapshot_model,
    workspace_from_model,
    workspace_model,
)


class SqlAlchemyContextWorkspaceRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def add(self, workspace: ContextWorkspace) -> None:
        with self._session_factory() as session:
            session.add(workspace_model(workspace))
            session.commit()

    def save(self, workspace: ContextWorkspace) -> None:
        with self._session_factory() as session:
            model = session.get(ContextWorkspaceModel, workspace.id)
            if model is None:
                session.add(workspace_model(workspace))
            else:
                apply_workspace(model, workspace)
            session.commit()

    def get(self, workspace_id: str) -> ContextWorkspace | None:
        with self._session_factory() as session:
            model = session.get(ContextWorkspaceModel, workspace_id.strip())
            if model is None:
                return None
            return workspace_from_model(model)

    def get_by_session(self, session_key: str) -> ContextWorkspace | None:
        with self._session_factory() as session:
            model = session.scalar(
                select(ContextWorkspaceModel).where(
                    ContextWorkspaceModel.session_key == session_key.strip(),
                ),
            )
            if model is None:
                return None
            return workspace_from_model(model)

    def list_recent(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[ContextWorkspace, ...]:
        with self._session_factory() as session:
            models = session.scalars(
                select(ContextWorkspaceModel)
                .order_by(
                    ContextWorkspaceModel.updated_at.desc(),
                    ContextWorkspaceModel.workspace_id.asc(),
                )
                .offset(max(0, int(offset)))
                .limit(max(1, min(int(limit), 500))),
            ).all()
            return tuple(workspace_from_model(model) for model in models)


class SqlAlchemyContextNodeRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def save(self, node: ContextNode) -> None:
        with self._session_factory() as session:
            model = _get_node_model(
                session,
                workspace_id=node.workspace_id,
                node_id=node.id,
            )
            if model is None:
                session.add(node_model(node))
            else:
                apply_node(model, node)
            session.commit()

    def save_many(self, nodes: tuple[ContextNode, ...]) -> None:
        if not nodes:
            return
        deduped_nodes = tuple(
            {
                (node.workspace_id, node.id): node
                for node in nodes
            }.values(),
        )
        with self._session_factory() as session:
            for node in deduped_nodes:
                model = _get_node_model(
                    session,
                    workspace_id=node.workspace_id,
                    node_id=node.id,
                )
                if model is None:
                    session.add(node_model(node))
                else:
                    apply_node(model, node)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                self._save_many_individually(deduped_nodes)

    def _save_many_individually(self, nodes: tuple[ContextNode, ...]) -> None:
        for node in nodes:
            self._save_one_with_retry(node)

    def _save_one_with_retry(self, node: ContextNode) -> None:
        with self._session_factory() as session:
            model = _get_node_model(
                session,
                workspace_id=node.workspace_id,
                node_id=node.id,
            )
            if model is None:
                session.add(node_model(node))
            else:
                apply_node(model, node)
            try:
                session.commit()
                return
            except IntegrityError:
                session.rollback()

            model = _get_node_model(
                session,
                workspace_id=node.workspace_id,
                node_id=node.id,
            )
            if model is None:
                raise RuntimeError(
                    "Context node upsert lost concurrent insert before retry.",
                )
            apply_node(model, node)
            session.commit()

    def delete_subtrees(
        self,
        *,
        workspace_id: str,
        root_node_ids: tuple[str, ...],
    ) -> None:
        normalized_workspace_id = workspace_id.strip()
        root_ids = {
            node_id.strip()
            for node_id in root_node_ids
            if isinstance(node_id, str) and node_id.strip()
        }
        if not normalized_workspace_id or not root_ids:
            return
        with self._session_factory() as session:
            models = session.scalars(
                select(ContextNodeStateModel).where(
                    ContextNodeStateModel.workspace_id == normalized_workspace_id,
                ),
            ).all()
            by_parent: dict[str | None, list[ContextNodeStateModel]] = {}
            by_id: dict[str, ContextNodeStateModel] = {}
            for model in models:
                by_id[model.node_id] = model
                by_parent.setdefault(model.parent_id, []).append(model)
            delete_ids = set(root_ids)
            queue = list(root_ids)
            while queue:
                parent_id = queue.pop()
                for child in by_parent.get(parent_id, ()):
                    if child.node_id in delete_ids:
                        continue
                    delete_ids.add(child.node_id)
                    queue.append(child.node_id)
            for node_id in delete_ids:
                model = by_id.get(node_id)
                if model is not None:
                    session.delete(model)
            session.commit()

    def get(self, *, workspace_id: str, node_id: str) -> ContextNode | None:
        with self._session_factory() as session:
            model = _get_node_model(
                session,
                workspace_id=workspace_id.strip(),
                node_id=node_id.strip(),
            )
            if model is None:
                return None
            return node_from_model(model)

    def list_for_workspace(self, workspace_id: str) -> tuple[ContextNode, ...]:
        with self._session_factory() as session:
            models = session.scalars(
                select(ContextNodeStateModel)
                .where(ContextNodeStateModel.workspace_id == workspace_id.strip())
                .order_by(
                    ContextNodeStateModel.display_order.asc(),
                    ContextNodeStateModel.node_id.asc(),
                ),
            ).all()
            return tuple(node_from_model(model) for model in models)

    def list_enabled_tool_schema_nodes(
        self,
        workspace_id: str,
    ) -> tuple[ContextNode, ...]:
        with self._session_factory() as session:
            models = session.scalars(
                select(ContextNodeStateModel)
                .where(
                    ContextNodeStateModel.workspace_id == workspace_id.strip(),
                    ContextNodeStateModel.owner == "tool",
                    ContextNodeStateModel.kind == "tool_function",
                )
                .order_by(
                    ContextNodeStateModel.display_order.asc(),
                    ContextNodeStateModel.node_id.asc(),
                ),
            ).all()
            return tuple(
                node
                for model in models
                for node in (node_from_model(model),)
                if node.state.schema_enabled
            )

    def list_tool_nodes_by_kind(
        self,
        workspace_id: str,
        *,
        kinds: tuple[str, ...],
    ) -> tuple[ContextNode, ...]:
        normalized_kinds = tuple(kind.strip() for kind in kinds if kind.strip())
        if not normalized_kinds:
            return ()
        with self._session_factory() as session:
            models = session.scalars(
                select(ContextNodeStateModel)
                .where(
                    ContextNodeStateModel.workspace_id == workspace_id.strip(),
                    ContextNodeStateModel.owner == "tool",
                    ContextNodeStateModel.kind.in_(normalized_kinds),
                )
                .order_by(
                    ContextNodeStateModel.display_order.asc(),
                    ContextNodeStateModel.node_id.asc(),
                ),
            ).all()
            return tuple(node_from_model(model) for model in models)


class SqlAlchemyContextOperationRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def add(self, operation: ContextTreeOperation) -> None:
        with self._session_factory() as session:
            session.add(operation_model(operation))
            session.commit()

    def list_for_workspace(
        self,
        workspace_id: str,
        *,
        limit: int | None = None,
    ) -> tuple[ContextTreeOperation, ...]:
        with self._session_factory() as session:
            statement = (
                select(ContextOperationModel)
                .where(ContextOperationModel.workspace_id == workspace_id.strip())
                .order_by(ContextOperationModel.created_at.asc())
            )
            models = session.scalars(statement).all()
            if limit is not None and limit > 0:
                models = models[-limit:]
            return tuple(operation_from_model(model) for model in models)


class SqlAlchemyContextSnapshotRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def add(self, snapshot: ContextSnapshot) -> None:
        with self._session_factory() as session:
            existing = session.get(ContextSnapshotModel, snapshot.id)
            if existing is None:
                session.add(snapshot_model(snapshot))
            else:
                apply_snapshot(existing, snapshot)
            session.commit()

    def get(self, snapshot_id: str) -> ContextSnapshot | None:
        with self._session_factory() as session:
            model = session.get(ContextSnapshotModel, snapshot_id.strip())
            if model is None:
                return None
            return snapshot_from_model(model)

    def get_by_run(self, run_id: str) -> ContextSnapshot | None:
        with self._session_factory() as session:
            model = session.scalar(
                select(ContextSnapshotModel)
                .where(ContextSnapshotModel.run_id == run_id.strip())
                .order_by(
                    ContextSnapshotModel.created_at.desc(),
                    ContextSnapshotModel.snapshot_id.desc(),
                ),
            )
            if model is None:
                return None
            return snapshot_from_model(model)

    def list_recent(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[ContextSnapshot, ...]:
        with self._session_factory() as session:
            models = session.scalars(
                select(ContextSnapshotModel)
                .order_by(
                    ContextSnapshotModel.created_at.desc(),
                    ContextSnapshotModel.snapshot_id.asc(),
                )
                .offset(max(0, int(offset)))
                .limit(max(1, min(int(limit), 500))),
            ).all()
            return tuple(snapshot_from_model(model) for model in models)


class SqlAlchemyContextRequestRenderSnapshotRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def add(self, snapshot: ContextRequestRenderSnapshot) -> None:
        with self._session_factory() as session:
            existing = session.get(ContextRequestRenderSnapshotModel, snapshot.id)
            if existing is None:
                session.add(request_render_snapshot_model(snapshot))
            else:
                apply_request_render_snapshot(existing, snapshot)
            session.commit()

    def get(self, snapshot_id: str) -> ContextRequestRenderSnapshot | None:
        with self._session_factory() as session:
            model = session.get(ContextRequestRenderSnapshotModel, snapshot_id.strip())
            if model is None:
                return None
            return request_render_snapshot_from_model(model)

    def get_by_run(self, run_id: str) -> ContextRequestRenderSnapshot | None:
        with self._session_factory() as session:
            model = session.scalar(
                select(ContextRequestRenderSnapshotModel)
                .where(ContextRequestRenderSnapshotModel.run_id == run_id.strip())
                .order_by(
                    ContextRequestRenderSnapshotModel.created_at.desc(),
                    ContextRequestRenderSnapshotModel.snapshot_id.desc(),
                ),
            )
            if model is None:
                return None
            return request_render_snapshot_from_model(model)

    def list_recent(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[ContextRequestRenderSnapshot, ...]:
        with self._session_factory() as session:
            models = session.scalars(
                select(ContextRequestRenderSnapshotModel)
                .order_by(
                    ContextRequestRenderSnapshotModel.created_at.desc(),
                    ContextRequestRenderSnapshotModel.snapshot_id.asc(),
                )
                .offset(max(0, int(offset)))
                .limit(max(1, min(int(limit), 500))),
            ).all()
            return tuple(request_render_snapshot_from_model(model) for model in models)


def _get_node_model(
    session,
    *,
    workspace_id: str,
    node_id: str,
) -> ContextNodeStateModel | None:
    return session.scalar(
        select(ContextNodeStateModel).where(
            ContextNodeStateModel.workspace_id == workspace_id,
            ContextNodeStateModel.node_id == node_id,
        ),
    )


__all__ = [
    "SqlAlchemyContextNodeRepository",
    "SqlAlchemyContextOperationRepository",
    "SqlAlchemyContextRequestRenderSnapshotRepository",
    "SqlAlchemyContextSnapshotRepository",
    "SqlAlchemyContextWorkspaceRepository",
]
