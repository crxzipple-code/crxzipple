from __future__ import annotations

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


def workspace_model(workspace: ContextWorkspace) -> ContextWorkspaceModel:
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


def apply_workspace(
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


def workspace_from_model(model: ContextWorkspaceModel) -> ContextWorkspace:
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


def node_model(node: ContextNode) -> ContextNodeStateModel:
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


def apply_node(model: ContextNodeStateModel, node: ContextNode) -> None:
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


def node_from_model(model: ContextNodeStateModel) -> ContextNode:
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


def operation_model(operation: ContextTreeOperation) -> ContextOperationModel:
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


def operation_from_model(model: ContextOperationModel) -> ContextTreeOperation:
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


def snapshot_model(snapshot: ContextSnapshot) -> ContextSnapshotModel:
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
        protocol_required_refs=[dict(ref) for ref in snapshot.protocol_required_refs],
        parent_snapshot_id=snapshot.parent_snapshot_id,
        parent_tree_revision=snapshot.parent_tree_revision,
        metadata_=dict(snapshot.metadata),
        created_at=snapshot.created_at,
    )


def apply_snapshot(
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
    model.protocol_required_refs = [dict(ref) for ref in snapshot.protocol_required_refs]
    model.parent_snapshot_id = snapshot.parent_snapshot_id
    model.parent_tree_revision = snapshot.parent_tree_revision
    model.metadata_ = dict(snapshot.metadata)
    model.created_at = snapshot.created_at


def snapshot_from_model(model: ContextSnapshotModel) -> ContextSnapshot:
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
        included_refs=ref_tuple(model.included_refs or ()),
        collapsed_refs=ref_tuple(model.collapsed_refs or ()),
        protocol_required_refs=ref_tuple(model.protocol_required_refs or ()),
        parent_snapshot_id=model.parent_snapshot_id,
        parent_tree_revision=model.parent_tree_revision,
        metadata=dict(model.metadata_ or {}),
        created_at=coerce_utc_datetime(model.created_at),
    )


def request_render_snapshot_model(
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
        projected_input_items=[dict(item) for item in snapshot.projected_input_items],
        tool_schema_refs=[dict(ref) for ref in snapshot.tool_schema_refs],
        resource_refs=[dict(ref) for ref in snapshot.resource_refs],
        request_hash=snapshot.request_hash,
        estimated_tokens=snapshot.estimated_tokens,
        render_report=dict(snapshot.render_report),
        timings=dict(snapshot.timings),
        metadata_=dict(snapshot.metadata),
        created_at=snapshot.created_at,
    )


def apply_request_render_snapshot(
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


def request_render_snapshot_from_model(
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
        input_item_refs=ref_tuple(model.input_item_refs or ()),
        projected_input_items=ref_tuple(model.projected_input_items or ()),
        tool_schema_refs=ref_tuple(model.tool_schema_refs or ()),
        resource_refs=ref_tuple(model.resource_refs or ()),
        request_hash=model.request_hash,
        estimated_tokens=model.estimated_tokens,
        render_report=dict(model.render_report or {}),
        timings=dict(model.timings or {}),
        metadata=dict(model.metadata_ or {}),
        created_at=coerce_utc_datetime(model.created_at),
    )


def ref_tuple(refs: object) -> tuple[dict[str, object], ...]:
    if not isinstance(refs, list | tuple):
        return ()
    return tuple(dict(ref) for ref in refs if isinstance(ref, dict))
