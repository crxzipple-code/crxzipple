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
    _orchestration_run_action_payload,
)
from crxzipple.modules.operations.interfaces.http_action_service import (
    operations_action_service,
)
from crxzipple.modules.operations.interfaces.http_models import (
    OperationsActionReasonRequest,
)
from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationRunNotFoundError,
    OrchestrationValidationError,
)

router = APIRouter()


@router.post(
    "/orchestration/runs/{run_id}/cancel",
    response_model=dict[str, Any],
)
def cancel_orchestration_run_from_operations(
    run_id: str,
    request: OperationsActionReasonRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    reason, audit_id = _begin_operations_action_audit(
        container,
        request,
        action_type="orchestration.run.cancel",
        target_type="orchestration_run",
        target_id=run_id,
        target={"run_id": run_id},
        default_reason="Operations orchestration run cancellation",
        risk="controlled",
    )
    try:
        run = operations_action_service(container).cancel_orchestration_run(
            run_id=run_id,
            reason=reason,
        )
    except OrchestrationRunNotFoundError as exc:
        http_exc = HTTPException(status_code=404, detail=str(exc))
        _mark_operations_action_failed(container, audit_id, http_exc)
        raise http_exc from None
    except OrchestrationValidationError as exc:
        http_exc = HTTPException(status_code=400, detail=str(exc))
        _mark_operations_action_failed(container, audit_id, http_exc)
        raise http_exc from None
    except Exception as exc:
        _mark_operations_action_failed(container, audit_id, exc)
        raise
    payload = _orchestration_run_action_payload(run)
    _mark_operations_action_succeeded(container, audit_id, payload)
    return payload


@router.post(
    "/orchestration/runs/{run_id}/resume",
    response_model=dict[str, Any],
)
def resume_orchestration_run_from_operations(
    run_id: str,
    request: OperationsActionReasonRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    reason, audit_id = _begin_operations_action_audit(
        container,
        request,
        action_type="orchestration.run.resume",
        target_type="orchestration_run",
        target_id=run_id,
        target={"run_id": run_id},
        default_reason="Operations orchestration run resume",
        risk="controlled",
    )
    try:
        run = operations_action_service(container).resume_orchestration_run(
            run_id=run_id,
            reason=reason,
        )
    except OrchestrationRunNotFoundError as exc:
        http_exc = HTTPException(status_code=404, detail=str(exc))
        _mark_operations_action_failed(container, audit_id, http_exc)
        raise http_exc from None
    except OrchestrationValidationError as exc:
        http_exc = HTTPException(status_code=400, detail=str(exc))
        _mark_operations_action_failed(container, audit_id, http_exc)
        raise http_exc from None
    except Exception as exc:
        _mark_operations_action_failed(container, audit_id, exc)
        raise
    payload = _orchestration_run_action_payload(run)
    _mark_operations_action_succeeded(container, audit_id, payload)
    return payload
