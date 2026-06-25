from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.runtime_container import AppContainer
from crxzipple.modules.operations.interfaces.http_action_audit import (
    _begin_operations_action_audit,
    _mark_operations_action_failed,
    _mark_operations_action_succeeded,
)
from crxzipple.modules.operations.interfaces.http_action_payloads import (
    _skill_package_payload,
)
from crxzipple.modules.operations.interfaces.http_action_service import (
    operations_action_service,
)
from crxzipple.modules.operations.interfaces.http_models import (
    OperationsSkillInstallRequest,
    OperationsSkillSyncRequest,
    OperationsSkillValidateRequest,
)
from crxzipple.modules.skills.domain import SkillError

router = APIRouter()


@router.post("/skills/validate", response_model=dict[str, Any])
def validate_skill_package_from_operations(
    request: OperationsSkillValidateRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    reason, audit_id = _begin_operations_action_audit(
        container,
        request,
        action_type="skills.package.validate",
        target_type="skill_package",
        target_id=request.path,
        target={"path": request.path},
        default_reason="Operations skill package validation",
        risk="controlled",
    )
    try:
        package = operations_action_service(container).validate_skill_package(
            path=request.path,
            reason=reason,
        )
    except SkillError as exc:
        http_exc = HTTPException(status_code=400, detail=str(exc))
        _mark_operations_action_failed(container, audit_id, http_exc)
        raise http_exc from exc
    except Exception as exc:
        _mark_operations_action_failed(container, audit_id, exc)
        raise
    payload = _skill_package_payload(package)
    _mark_operations_action_succeeded(container, audit_id, payload)
    return payload


@router.post("/skills/install", response_model=dict[str, Any])
def install_global_skill_from_operations(
    request: OperationsSkillInstallRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    reason, audit_id = _begin_operations_action_audit(
        container,
        request,
        action_type="skills.global.install",
        target_type="skill_package",
        target_id=request.source_dir,
        target={"source_dir": request.source_dir},
        default_reason="Operations global skill install",
        risk="controlled",
    )
    try:
        result = operations_action_service(container).install_global_skill(
            source_dir=request.source_dir,
            reason=reason,
        )
    except SkillError as exc:
        http_exc = HTTPException(status_code=400, detail=str(exc))
        _mark_operations_action_failed(container, audit_id, http_exc)
        raise http_exc from exc
    except Exception as exc:
        _mark_operations_action_failed(container, audit_id, exc)
        raise
    payload = {
        "scope": result.scope.value,
        "target_root": result.target_root,
        "target_path": result.target_path,
        "skill": _skill_package_payload(result.package),
    }
    _mark_operations_action_succeeded(container, audit_id, payload)
    return payload


@router.post("/skills/sync", response_model=dict[str, Any])
def sync_skills_from_operations(
    request: OperationsSkillSyncRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    target_id = request.source_id or request.workspace_dir or "all"
    reason, audit_id = _begin_operations_action_audit(
        container,
        request,
        action_type="skills.source.sync",
        target_type="skill_source",
        target_id=target_id,
        target={
            "workspace_dir": request.workspace_dir,
            "source_id": request.source_id,
            "surface": request.surface,
        },
        default_reason="Operations skill source sync",
        risk="controlled",
    )
    try:
        result = operations_action_service(container).sync_skills(
            workspace_dir=request.workspace_dir,
            source_id=request.source_id,
            surface=request.surface,
            reason=reason,
        )
    except SkillError as exc:
        http_exc = HTTPException(status_code=400, detail=str(exc))
        _mark_operations_action_failed(container, audit_id, http_exc)
        raise http_exc from exc
    except Exception as exc:
        _mark_operations_action_failed(container, audit_id, exc)
        raise
    payload = {
        "source_id": result.source_id,
        "synced_count": result.synced_count,
        "skills": [_skill_package_payload(package) for package in result.packages],
    }
    _mark_operations_action_succeeded(container, audit_id, payload)
    return payload
