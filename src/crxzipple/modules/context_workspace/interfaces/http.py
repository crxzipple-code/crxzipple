from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.modules.context_workspace.application import (
    ContextActionInput,
    EnsureContextWorkspaceInput,
    RecordContextRenderSnapshotInput,
    RenderContextPromptInput,
)
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextActionNotAllowedError,
    ContextActor,
    ContextActorKind,
    ContextEstimate,
    ContextNode,
    ContextNodeNotFoundError,
    ContextRenderSnapshot,
    ContextRenderSnapshotNotFoundError,
    ContextWorkspace,
    ContextWorkspaceNotFoundError,
)


router = APIRouter()


class EnsureWorkspaceRequest(BaseModel):
    agent_id: str = Field(min_length=1)
    metadata: dict[str, object] = Field(default_factory=dict)


class ContextActionRequest(BaseModel):
    actor_kind: ContextActorKind = ContextActorKind.USER
    actor_id: str | None = None
    run_id: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)


class RecordSnapshotRequest(BaseModel):
    run_id: str = Field(min_length=1)
    prompt_body: str = Field(min_length=1)
    provider_attachments: dict[str, object] = Field(default_factory=dict)
    estimate: dict[str, object] = Field(default_factory=dict)
    included_node_ids: list[str] = Field(default_factory=list)
    mirrored_node_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


@router.post(
    "/by-session/{session_key}/ensure",
    status_code=status.HTTP_201_CREATED,
)
def ensure_workspace(
    session_key: str,
    payload: EnsureWorkspaceRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    workspace = container.require(AppKey.CONTEXT_WORKSPACE_SERVICE).ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key=session_key,
            agent_id=payload.agent_id,
            metadata=payload.metadata,
        ),
    )
    return {"workspace": _workspace_payload(workspace)}


@router.get("/by-session/{session_key}/tree")
def get_tree(
    session_key: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        view = container.require(AppKey.CONTEXT_TREE_SERVICE).list_tree(session_key)
    except ContextWorkspaceNotFoundError as exc:
        raise _not_found(exc) from None
    return _tree_payload(view.workspace, view.nodes, view.estimate)


@router.get("/by-session/{session_key}/estimate")
def get_estimate(
    session_key: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        view = container.require(AppKey.CONTEXT_TREE_SERVICE).list_tree(session_key)
    except ContextWorkspaceNotFoundError as exc:
        raise _not_found(exc) from None
    return {
        "workspace": _workspace_payload(view.workspace),
        "estimate": view.estimate.to_payload(),
    }


@router.post("/by-session/{session_key}/render")
def render_prompt_body(
    session_key: str,
    container: Annotated[AppContainer, Depends(get_container)],
    run_id: Annotated[str | None, Query()] = None,
) -> dict[str, object]:
    try:
        result = container.require(AppKey.CONTEXT_RENDER_SERVICE).render_prompt_body(
            RenderContextPromptInput(session_key=session_key, run_id=run_id),
        )
    except ContextWorkspaceNotFoundError as exc:
        raise _not_found(exc) from None
    return {
        "workspace": _workspace_payload(result.workspace),
        "prompt_body": result.prompt_body,
        "estimate": result.estimate.to_payload(),
        "included_node_ids": list(result.included_node_ids),
    }


@router.post("/by-session/{session_key}/render-snapshots")
def record_render_snapshot(
    session_key: str,
    payload: RecordSnapshotRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        snapshot = container.require(AppKey.CONTEXT_RENDER_SERVICE).record_render_snapshot(
            RecordContextRenderSnapshotInput(
                session_key=session_key,
                run_id=payload.run_id,
                prompt_body=payload.prompt_body,
                provider_attachments=payload.provider_attachments,
                estimate=ContextEstimate.from_payload(payload.estimate),
                included_node_ids=tuple(payload.included_node_ids),
                mirrored_node_ids=tuple(payload.mirrored_node_ids),
                metadata=payload.metadata,
            ),
        )
    except ContextWorkspaceNotFoundError as exc:
        raise _not_found(exc) from None
    return {"snapshot": _snapshot_payload(snapshot)}


@router.get("/runs/{run_id}/render-snapshot")
def get_render_snapshot(
    run_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        snapshot = container.require(AppKey.CONTEXT_RENDER_SERVICE).get_snapshot_by_run(
            run_id,
        )
    except ContextRenderSnapshotNotFoundError as exc:
        raise _not_found(exc) from None
    return {"snapshot": _snapshot_payload(snapshot)}


@router.post("/by-session/{session_key}/nodes/{node_id}/actions/{action}")
def apply_node_action(
    session_key: str,
    node_id: str,
    action: str,
    payload: ContextActionRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    resolved_action = _parse_action(action)
    try:
        result = container.require(AppKey.CONTEXT_TREE_SERVICE).apply_action(
            ContextActionInput(
                session_key=session_key,
                node_id=node_id,
                action=resolved_action,
                actor=ContextActor(
                    kind=payload.actor_kind,
                    actor_id=payload.actor_id,
                ),
                run_id=payload.run_id,
                payload=payload.payload,
            ),
        )
    except (ContextWorkspaceNotFoundError, ContextNodeNotFoundError) as exc:
        raise _not_found(exc) from None
    except ContextActionNotAllowedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {
        "workspace": _workspace_payload(result.workspace),
        "node": _node_payload(result.node),
        "action": result.action.value,
        "operation_id": result.operation_id,
    }


def _parse_action(raw: str) -> ContextAction:
    normalized = raw.strip().replace("-", "_")
    try:
        return ContextAction(normalized)
    except ValueError as exc:
        allowed = ", ".join(action.value.replace("_", "-") for action in ContextAction)
        raise HTTPException(
            status_code=400,
            detail=f"Unknown context action '{raw}'. Allowed actions: {allowed}",
        ) from exc


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


def _workspace_payload(workspace: ContextWorkspace) -> dict[str, object]:
    return {
        "id": workspace.id,
        "session_key": workspace.session_key,
        "agent_id": workspace.agent_id,
        "status": workspace.status,
        "active_revision": workspace.active_revision,
        "metadata": dict(workspace.metadata),
        "created_at": workspace.created_at.isoformat(),
        "updated_at": workspace.updated_at.isoformat(),
    }


def _node_payload(node: ContextNode) -> dict[str, object]:
    return {
        "id": node.id,
        "workspace_id": node.workspace_id,
        "parent_id": node.parent_id,
        "owner": node.owner,
        "kind": node.kind,
        "title": node.title,
        "summary": node.summary,
        "state": node.state.to_payload(),
        "actions": [action.value for action in node.actions],
        "owner_ref": dict(node.owner_ref),
        "estimate": node.estimate.to_payload(),
        "revision": node.revision,
        "freshness": node.freshness,
        "display_order": node.display_order,
        "metadata": dict(node.metadata),
        "created_at": node.created_at.isoformat(),
        "updated_at": node.updated_at.isoformat(),
    }


def _tree_payload(
    workspace: ContextWorkspace,
    nodes: tuple[ContextNode, ...],
    estimate: ContextEstimate,
) -> dict[str, object]:
    return {
        "workspace": _workspace_payload(workspace),
        "nodes": [_node_payload(node) for node in nodes],
        "estimate": estimate.to_payload(),
    }


def _snapshot_payload(snapshot: ContextRenderSnapshot) -> dict[str, object]:
    return {
        "id": snapshot.id,
        "workspace_id": snapshot.workspace_id,
        "session_key": snapshot.session_key,
        "run_id": snapshot.run_id,
        "tree_revision": snapshot.tree_revision,
        "prompt_body": snapshot.prompt_body,
        "provider_attachments": dict(snapshot.provider_attachments),
        "estimate": snapshot.estimate.to_payload(),
        "included_node_ids": list(snapshot.included_node_ids),
        "mirrored_node_ids": list(snapshot.mirrored_node_ids),
        "metadata": dict(snapshot.metadata),
        "created_at": snapshot.created_at.isoformat(),
    }


__all__ = ["router"]
