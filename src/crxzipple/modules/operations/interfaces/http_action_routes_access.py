from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.runtime_container import AppContainer
from crxzipple.modules.access.interfaces.presenters import (
    present_readiness,
    present_setup_flow,
)
from crxzipple.modules.operations.interfaces.http_action_audit import (
    _begin_operations_action_audit,
    _mark_operations_action_failed,
    _mark_operations_action_succeeded,
)
from crxzipple.modules.operations.interfaces.http_action_service import (
    operations_action_service,
)
from crxzipple.modules.operations.interfaces.http_models import (
    OperationsAccessCheckRequest,
)

router = APIRouter()


@router.get("/access/inventory", response_model=dict[str, Any])
def get_access_inventory_from_operations(
    container: Annotated[AppContainer, Depends(get_container)],
    workspace_dir: str | None = Query(default=None),
    include_ready: bool = Query(default=True),
    include_disabled: bool = Query(default=False),
) -> dict[str, Any]:
    payload = operations_action_service(container).collect_access_inventory(
        workspace_dir=workspace_dir,
        include_ready=include_ready,
        include_disabled=include_disabled,
    )
    return payload


@router.post("/access/check", response_model=dict[str, Any])
def check_access_from_operations(
    request: OperationsAccessCheckRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    _reason, audit_id = _begin_operations_action_audit(
        container,
        request,
        action_type="access.readiness.check",
        target_type="access_readiness",
        target={
            "requirements": request.requirements,
            "credential_bindings": request.credential_bindings,
            "workspace_dir": request.workspace_dir,
        },
        default_reason="Operations access readiness check",
    )
    try:
        readiness_items = operations_action_service(container).check_access_readiness(
            requirements=request.requirements,
            credential_bindings=request.credential_bindings,
            workspace_dir=request.workspace_dir,
            allow_literal_credentials=request.allow_literal_credentials,
        )
        checks = [
            present_readiness(readiness, target_type=target_type)
            for target_type, readiness in readiness_items
        ]
    except Exception as exc:
        _mark_operations_action_failed(container, audit_id, exc)
        raise
    payload = {
        "ready": all(bool(check["ready"]) for check in checks),
        "checks": checks,
    }
    _mark_operations_action_succeeded(container, audit_id, payload)
    return payload


@router.get("/access/setup", response_model=dict[str, Any])
def get_access_setup_from_operations(
    target: Annotated[str, Query(...)],
    container: Annotated[AppContainer, Depends(get_container)],
    workspace_dir: str | None = Query(default=None),
) -> dict[str, Any]:
    flow = operations_action_service(container).begin_access_setup(
        target=target,
        workspace_dir=workspace_dir,
    )
    return present_setup_flow(flow)
