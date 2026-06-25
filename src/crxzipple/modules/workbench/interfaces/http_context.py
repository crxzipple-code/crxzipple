from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.modules.context_workspace.application import ContextActionInput
from crxzipple.modules.context_workspace.domain import (
    ContextActionNotAllowedError,
    ContextActor,
    ContextNodeNotFoundError,
    ContextSnapshotNotFoundError,
    ContextWorkspaceNotFoundError,
)
from crxzipple.modules.context_workspace.interfaces.http import (
    ContextActionRequest,
    _node_payload as context_node_payload,
    _parse_action as parse_context_action,
    _snapshot_payload as context_snapshot_payload,
    _tree_payload as context_tree_payload,
    _workspace_payload as context_workspace_payload,
)
from crxzipple.modules.workbench.interfaces.http_dependencies import context_not_found


router = APIRouter()


@router.get("/workbench/context-tree/by-session/{session_key}")
def get_workbench_context_tree(
    session_key: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        view = container.require(AppKey.CONTEXT_TREE_SERVICE).list_tree(session_key)
    except ContextWorkspaceNotFoundError as exc:
        raise context_not_found(exc) from None
    return context_tree_payload(view.workspace, view.nodes, view.estimate)


@router.post("/workbench/context-tree/by-session/{session_key}/nodes/{node_id}/actions/{action}")
def apply_workbench_context_action(
    session_key: str,
    node_id: str,
    action: str,
    payload: ContextActionRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    resolved_action = parse_context_action(action)
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
        raise context_not_found(exc) from None
    except ContextActionNotAllowedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {
        "workspace": context_workspace_payload(result.workspace),
        "node": context_node_payload(result.node),
        "action": result.action.value,
        "operation_id": result.operation_id,
    }


@router.get("/workbench/context-snapshots/runs/{run_id}")
def get_workbench_context_snapshot(
    run_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    include_debug_body: Annotated[bool, Query()] = False,
) -> dict[str, object]:
    try:
        snapshot = container.require(
            AppKey.CONTEXT_OBSERVATION_SNAPSHOT_SERVICE,
        ).get_snapshot_by_run(run_id)
    except ContextSnapshotNotFoundError as exc:
        raise context_not_found(exc) from None
    return {
        "snapshot": context_snapshot_payload(
            snapshot,
            include_debug_body=include_debug_body,
        ),
    }


@router.get("/workbench/context-snapshots/{snapshot_id}")
def get_workbench_context_snapshot_by_id(
    snapshot_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    include_debug_body: Annotated[bool, Query()] = False,
) -> dict[str, object]:
    try:
        snapshot = container.require(
            AppKey.CONTEXT_OBSERVATION_SNAPSHOT_SERVICE,
        ).get_snapshot(snapshot_id)
    except ContextSnapshotNotFoundError as exc:
        raise context_not_found(exc) from None
    return {
        "snapshot": context_snapshot_payload(
            snapshot,
            include_debug_body=include_debug_body,
        ),
    }
