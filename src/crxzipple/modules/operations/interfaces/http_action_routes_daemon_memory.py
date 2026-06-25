from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.runtime_container import AppContainer
from crxzipple.modules.daemon import DaemonNotFoundError, DaemonValidationError
from crxzipple.modules.daemon.interfaces.presenters import instance_payload
from crxzipple.modules.operations.interfaces.http_action_audit import (
    _begin_operations_action_audit,
    _daemon_service_action_risk,
    _mark_operations_action_failed,
    _mark_operations_action_succeeded,
)
from crxzipple.modules.operations.interfaces.http_action_service import (
    operations_action_service,
)
from crxzipple.modules.operations.interfaces.http_models import (
    OperationsDaemonServiceActionRequest,
    OperationsMemoryWriteLongTermRequest,
    OperationsMemoryWriteResultResponse,
)

router = APIRouter()


@router.post(
    "/daemon/services/{service_key}/{action}",
    response_model=list[dict[str, Any]],
)
def run_daemon_service_action_from_operations(
    service_key: str,
    action: str,
    request: OperationsDaemonServiceActionRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[dict[str, Any]]:
    normalized_action = action.strip().lower()
    reason, audit_id = _begin_operations_action_audit(
        container,
        request,
        action_type=f"daemon.service.{normalized_action}",
        target_type="daemon_service",
        target_id=service_key,
        target={"service_key": service_key, "action": normalized_action},
        default_reason=f"Operations daemon action {normalized_action} for {service_key}",
        risk=_daemon_service_action_risk(normalized_action),
    )
    try:
        instances = operations_action_service(container).run_daemon_service_action(
            service_key=service_key,
            action=action,
            reason=reason,
        )
    except (DaemonValidationError, DaemonNotFoundError, ValueError) as exc:
        http_exc = HTTPException(status_code=400, detail=str(exc))
        _mark_operations_action_failed(container, audit_id, http_exc)
        raise http_exc from exc
    except Exception as exc:
        _mark_operations_action_failed(container, audit_id, exc)
        raise
    payload = [instance_payload(instance) for instance in instances]
    _mark_operations_action_succeeded(container, audit_id, payload)
    return payload


@router.post(
    "/memory/long-term",
    response_model=OperationsMemoryWriteResultResponse,
)
def write_long_term_memory_from_operations(
    request: OperationsMemoryWriteLongTermRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OperationsMemoryWriteResultResponse:
    reason, audit_id = _begin_operations_action_audit(
        container,
        request,
        action_type="memory.long_term.write",
        target_type="agent_memory",
        target_id=request.agent_id,
        target={"agent_id": request.agent_id},
        default_reason="Operations long-term memory write",
        risk="controlled",
    )
    try:
        result = operations_action_service(container).write_long_term_memory(
            agent_id=request.agent_id,
            content=request.content,
            reason=reason,
        )
    except LookupError as exc:
        http_exc = HTTPException(status_code=404, detail=str(exc))
        _mark_operations_action_failed(container, audit_id, http_exc)
        raise http_exc from exc
    except Exception as exc:
        _mark_operations_action_failed(container, audit_id, exc)
        raise
    write_result = getattr(result, "write_result", None)
    if write_result is None:
        http_exc = HTTPException(
            status_code=500, detail="Memory write did not return a result."
        )
        _mark_operations_action_failed(container, audit_id, http_exc)
        raise http_exc
    response = OperationsMemoryWriteResultResponse(
        path=write_result.path,
        line_start=write_result.line_start,
        line_end=write_result.line_end,
        kind=write_result.kind,
    )
    _mark_operations_action_succeeded(container, audit_id, response)
    return response
