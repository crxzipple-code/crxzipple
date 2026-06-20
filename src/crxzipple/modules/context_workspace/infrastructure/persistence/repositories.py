from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from crxzipple.core.db import SessionFactory
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextActor,
    ContextActorKind,
    ContextEstimate,
    ContextNode,
    ContextNodeState,
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
from crxzipple.shared.time import coerce_utc_datetime


class SqlAlchemyContextWorkspaceRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def add(self, workspace: ContextWorkspace) -> None:
        with self._session_factory() as session:
            session.add(_workspace_model(workspace))
            session.commit()

    def save(self, workspace: ContextWorkspace) -> None:
        with self._session_factory() as session:
            model = session.get(ContextWorkspaceModel, workspace.id)
            if model is None:
                session.add(_workspace_model(workspace))
            else:
                _apply_workspace(model, workspace)
            session.commit()

    def get(self, workspace_id: str) -> ContextWorkspace | None:
        with self._session_factory() as session:
            model = session.get(ContextWorkspaceModel, workspace_id.strip())
            if model is None:
                return None
            return _workspace_from_model(model)

    def get_by_session(self, session_key: str) -> ContextWorkspace | None:
        with self._session_factory() as session:
            model = session.scalar(
                select(ContextWorkspaceModel).where(
                    ContextWorkspaceModel.session_key == session_key.strip(),
                ),
            )
            if model is None:
                return None
            return _workspace_from_model(model)

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
            return tuple(_workspace_from_model(model) for model in models)


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
                session.add(_node_model(node))
            else:
                _apply_node(model, node)
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
                    session.add(_node_model(node))
                else:
                    _apply_node(model, node)
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
                session.add(_node_model(node))
            else:
                _apply_node(model, node)
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
            _apply_node(model, node)
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
            return _node_from_model(model)

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
            return tuple(_node_from_model(model) for model in models)

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
                for node in (_node_from_model(model),)
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
            return tuple(_node_from_model(model) for model in models)


class SqlAlchemyContextOperationRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def add(self, operation: ContextTreeOperation) -> None:
        with self._session_factory() as session:
            session.add(_operation_model(operation))
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
            return tuple(_operation_from_model(model) for model in models)


class SqlAlchemyContextSnapshotRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def add(self, snapshot: ContextSnapshot) -> None:
        with self._session_factory() as session:
            existing = session.get(ContextSnapshotModel, snapshot.id)
            if existing is None:
                session.add(_snapshot_model(snapshot))
            else:
                _apply_snapshot(existing, snapshot)
            session.commit()

    def get(self, snapshot_id: str) -> ContextSnapshot | None:
        with self._session_factory() as session:
            model = session.get(ContextSnapshotModel, snapshot_id.strip())
            if model is None:
                return None
            return _snapshot_from_model(model)

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
            return _snapshot_from_model(model)

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
            return tuple(_snapshot_from_model(model) for model in models)


class SqlAlchemyContextRequestRenderSnapshotRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def add(self, snapshot: ContextRequestRenderSnapshot) -> None:
        with self._session_factory() as session:
            existing = session.get(ContextRequestRenderSnapshotModel, snapshot.id)
            if existing is None:
                session.add(_request_render_snapshot_model(snapshot))
            else:
                _apply_request_render_snapshot(existing, snapshot)
            session.commit()

    def get(self, snapshot_id: str) -> ContextRequestRenderSnapshot | None:
        with self._session_factory() as session:
            model = session.get(ContextRequestRenderSnapshotModel, snapshot_id.strip())
            if model is None:
                return None
            return _request_render_snapshot_from_model(model)

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
            return _request_render_snapshot_from_model(model)

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
            return tuple(_request_render_snapshot_from_model(model) for model in models)


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


def _workspace_model(workspace: ContextWorkspace) -> ContextWorkspaceModel:
    return ContextWorkspaceModel(
        workspace_id=workspace.id,
        session_key=workspace.session_key,
        agent_id=workspace.agent_id,
        status=workspace.status,
        active_revision=workspace.active_revision,
        metadata_=dict(workspace.metadata),
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )


def _apply_workspace(
    model: ContextWorkspaceModel,
    workspace: ContextWorkspace,
) -> None:
    model.session_key = workspace.session_key
    model.agent_id = workspace.agent_id
    model.status = workspace.status
    model.active_revision = workspace.active_revision
    model.metadata_ = dict(workspace.metadata)
    model.created_at = workspace.created_at
    model.updated_at = workspace.updated_at


def _workspace_from_model(model: ContextWorkspaceModel) -> ContextWorkspace:
    return ContextWorkspace(
        id=model.workspace_id,
        session_key=model.session_key,
        agent_id=model.agent_id,
        status=model.status,
        active_revision=model.active_revision,
        metadata=dict(model.metadata_ or {}),
        created_at=coerce_utc_datetime(model.created_at),
        updated_at=coerce_utc_datetime(model.updated_at),
    )


def _node_model(node: ContextNode) -> ContextNodeStateModel:
    return ContextNodeStateModel(
        workspace_id=node.workspace_id,
        node_id=node.id,
        parent_id=node.parent_id,
        owner=node.owner,
        kind=node.kind,
        title=node.title,
        summary=node.summary,
        content=node.content,
        state=node.state.to_payload(),
        actions=[action.value for action in node.actions],
        owner_ref=dict(node.owner_ref),
        estimate=node.estimate.to_payload(),
        revision=node.revision,
        freshness=node.freshness,
        display_order=node.display_order,
        metadata_=dict(node.metadata),
        created_at=node.created_at,
        updated_at=node.updated_at,
    )


def _apply_node(model: ContextNodeStateModel, node: ContextNode) -> None:
    model.parent_id = node.parent_id
    model.owner = node.owner
    model.kind = node.kind
    model.title = node.title
    model.summary = node.summary
    model.content = node.content
    model.state = node.state.to_payload()
    model.actions = [action.value for action in node.actions]
    model.owner_ref = dict(node.owner_ref)
    model.estimate = node.estimate.to_payload()
    model.revision = node.revision
    model.freshness = node.freshness
    model.display_order = node.display_order
    model.metadata_ = dict(node.metadata)
    model.created_at = node.created_at
    model.updated_at = node.updated_at


def _node_from_model(model: ContextNodeStateModel) -> ContextNode:
    return ContextNode(
        id=model.node_id,
        workspace_id=model.workspace_id,
        parent_id=model.parent_id,
        owner=model.owner,
        kind=model.kind,
        title=model.title,
        summary=model.summary,
        content=model.content,
        state=ContextNodeState.from_payload(dict(model.state or {})),
        actions=tuple(ContextAction(action) for action in model.actions or ()),
        owner_ref=dict(model.owner_ref or {}),
        estimate=ContextEstimate.from_payload(dict(model.estimate or {})),
        revision=model.revision,
        freshness=model.freshness,
        display_order=model.display_order,
        metadata=dict(model.metadata_ or {}),
        created_at=coerce_utc_datetime(model.created_at),
        updated_at=coerce_utc_datetime(model.updated_at),
    )


def _operation_model(operation: ContextTreeOperation) -> ContextOperationModel:
    return ContextOperationModel(
        operation_id=operation.id,
        workspace_id=operation.workspace_id,
        session_key=operation.session_key,
        run_id=operation.run_id,
        node_id=operation.node_id,
        action=operation.action.value,
        actor_kind=operation.actor.kind.value,
        actor_id=operation.actor.actor_id,
        status=operation.status,
        reason=operation.reason,
        payload=dict(operation.payload),
        result=dict(operation.result) if operation.result is not None else None,
        tree_revision=operation.tree_revision,
        created_at=operation.created_at,
    )


def _operation_from_model(model: ContextOperationModel) -> ContextTreeOperation:
    return ContextTreeOperation(
        id=model.operation_id,
        workspace_id=model.workspace_id,
        session_key=model.session_key,
        run_id=model.run_id,
        node_id=model.node_id,
        action=ContextAction(model.action),
        actor=ContextActor(
            kind=ContextActorKind(model.actor_kind),
            actor_id=model.actor_id,
        ),
        status=model.status,
        reason=model.reason,
        payload=dict(model.payload or {}),
        result=dict(model.result) if model.result is not None else None,
        tree_revision=model.tree_revision,
        created_at=coerce_utc_datetime(model.created_at),
    )


def _snapshot_model(snapshot: ContextSnapshot) -> ContextSnapshotModel:
    return ContextSnapshotModel(
        snapshot_id=snapshot.id,
        workspace_id=snapshot.workspace_id,
        session_key=snapshot.session_key,
        run_id=snapshot.run_id,
        tree_revision=snapshot.tree_revision,
        debug_body=snapshot.debug_body,
        provider_attachments=dict(snapshot.provider_attachments),
        estimate=snapshot.estimate.to_payload(),
        included_node_ids=list(snapshot.included_node_ids),
        mirrored_node_ids=list(snapshot.mirrored_node_ids),
        included_refs=[dict(ref) for ref in snapshot.included_refs],
        collapsed_refs=[dict(ref) for ref in snapshot.collapsed_refs],
        protocol_required_refs=[
            dict(ref) for ref in snapshot.protocol_required_refs
        ],
        parent_snapshot_id=snapshot.parent_snapshot_id,
        parent_tree_revision=snapshot.parent_tree_revision,
        metadata_=dict(snapshot.metadata),
        created_at=snapshot.created_at,
    )


def _apply_snapshot(
    model: ContextSnapshotModel,
    snapshot: ContextSnapshot,
) -> None:
    model.snapshot_id = snapshot.id
    model.workspace_id = snapshot.workspace_id
    model.session_key = snapshot.session_key
    model.run_id = snapshot.run_id
    model.tree_revision = snapshot.tree_revision
    model.debug_body = snapshot.debug_body
    model.provider_attachments = dict(snapshot.provider_attachments)
    model.estimate = snapshot.estimate.to_payload()
    model.included_node_ids = list(snapshot.included_node_ids)
    model.mirrored_node_ids = list(snapshot.mirrored_node_ids)
    model.included_refs = [dict(ref) for ref in snapshot.included_refs]
    model.collapsed_refs = [dict(ref) for ref in snapshot.collapsed_refs]
    model.protocol_required_refs = [
        dict(ref) for ref in snapshot.protocol_required_refs
    ]
    model.parent_snapshot_id = snapshot.parent_snapshot_id
    model.parent_tree_revision = snapshot.parent_tree_revision
    model.metadata_ = dict(snapshot.metadata)
    model.created_at = snapshot.created_at


def _snapshot_from_model(model: ContextSnapshotModel) -> ContextSnapshot:
    return ContextSnapshot(
        id=model.snapshot_id,
        workspace_id=model.workspace_id,
        session_key=model.session_key,
        run_id=model.run_id,
        tree_revision=model.tree_revision,
        debug_body=model.debug_body,
        provider_attachments=dict(model.provider_attachments or {}),
        estimate=ContextEstimate.from_payload(dict(model.estimate or {})),
        included_node_ids=tuple(model.included_node_ids or ()),
        mirrored_node_ids=tuple(model.mirrored_node_ids or ()),
        included_refs=_ref_tuple(model.included_refs or ()),
        collapsed_refs=_ref_tuple(model.collapsed_refs or ()),
        protocol_required_refs=_ref_tuple(model.protocol_required_refs or ()),
        parent_snapshot_id=model.parent_snapshot_id,
        parent_tree_revision=model.parent_tree_revision,
        metadata=dict(model.metadata_ or {}),
        created_at=coerce_utc_datetime(model.created_at),
    )


def _ref_tuple(refs: object) -> tuple[dict[str, object], ...]:
    if not isinstance(refs, list | tuple):
        return ()
    return tuple(dict(ref) for ref in refs if isinstance(ref, dict))


def _request_render_snapshot_model(
    snapshot: ContextRequestRenderSnapshot,
) -> ContextRequestRenderSnapshotModel:
    return ContextRequestRenderSnapshotModel(
        snapshot_id=snapshot.id,
        workspace_id=snapshot.workspace_id,
        session_key=snapshot.session_key,
        run_id=snapshot.run_id,
        tree_revision=snapshot.tree_revision,
        turn_id=snapshot.turn_id,
        step_id=snapshot.step_id,
        llm_invocation_id=snapshot.llm_invocation_id,
        provider=snapshot.provider,
        transport=snapshot.transport,
        model=snapshot.model,
        renderer_id=snapshot.renderer_id,
        renderer_version=snapshot.renderer_version,
        session_frontier_revision=snapshot.session_frontier_revision,
        input_item_refs=[dict(ref) for ref in snapshot.input_item_refs],
        projected_input_items=[
            dict(item) for item in snapshot.projected_input_items
        ],
        tool_schema_refs=[dict(ref) for ref in snapshot.tool_schema_refs],
        resource_refs=[dict(ref) for ref in snapshot.resource_refs],
        request_hash=snapshot.request_hash,
        estimated_tokens=snapshot.estimated_tokens,
        render_report=dict(snapshot.render_report),
        timings=dict(snapshot.timings),
        metadata_=dict(snapshot.metadata),
        created_at=snapshot.created_at,
    )


def _apply_request_render_snapshot(
    model: ContextRequestRenderSnapshotModel,
    snapshot: ContextRequestRenderSnapshot,
) -> None:
    model.workspace_id = snapshot.workspace_id
    model.session_key = snapshot.session_key
    model.run_id = snapshot.run_id
    model.tree_revision = snapshot.tree_revision
    model.turn_id = snapshot.turn_id
    model.step_id = snapshot.step_id
    model.llm_invocation_id = snapshot.llm_invocation_id
    model.provider = snapshot.provider
    model.transport = snapshot.transport
    model.model = snapshot.model
    model.renderer_id = snapshot.renderer_id
    model.renderer_version = snapshot.renderer_version
    model.session_frontier_revision = snapshot.session_frontier_revision
    model.input_item_refs = [dict(ref) for ref in snapshot.input_item_refs]
    model.projected_input_items = [
        dict(item) for item in snapshot.projected_input_items
    ]
    model.tool_schema_refs = [dict(ref) for ref in snapshot.tool_schema_refs]
    model.resource_refs = [dict(ref) for ref in snapshot.resource_refs]
    model.request_hash = snapshot.request_hash
    model.estimated_tokens = snapshot.estimated_tokens
    model.render_report = dict(snapshot.render_report)
    model.timings = dict(snapshot.timings)
    model.metadata_ = dict(snapshot.metadata)
    model.created_at = snapshot.created_at


def _request_render_snapshot_from_model(
    model: ContextRequestRenderSnapshotModel,
) -> ContextRequestRenderSnapshot:
    return ContextRequestRenderSnapshot(
        id=model.snapshot_id,
        workspace_id=model.workspace_id,
        session_key=model.session_key,
        run_id=model.run_id,
        tree_revision=model.tree_revision,
        turn_id=model.turn_id,
        step_id=model.step_id,
        llm_invocation_id=model.llm_invocation_id,
        provider=model.provider,
        transport=model.transport,
        model=model.model,
        renderer_id=model.renderer_id,
        renderer_version=model.renderer_version,
        session_frontier_revision=model.session_frontier_revision,
        input_item_refs=_ref_tuple(model.input_item_refs or ()),
        projected_input_items=_ref_tuple(model.projected_input_items or ()),
        tool_schema_refs=_ref_tuple(model.tool_schema_refs or ()),
        resource_refs=_ref_tuple(model.resource_refs or ()),
        request_hash=model.request_hash,
        estimated_tokens=model.estimated_tokens,
        render_report=dict(model.render_report or {}),
        timings=dict(model.timings or {}),
        metadata=dict(model.metadata_ or {}),
        created_at=coerce_utc_datetime(model.created_at),
    )


__all__ = [
    "SqlAlchemyContextNodeRepository",
    "SqlAlchemyContextOperationRepository",
    "SqlAlchemyContextRequestRenderSnapshotRepository",
    "SqlAlchemyContextSnapshotRepository",
    "SqlAlchemyContextWorkspaceRepository",
]
