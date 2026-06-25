from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from crxzipple.interfaces.authorization import authorize_tool_run
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.modules.operations.interfaces.http_action_audit import (
    _begin_operations_action_audit,
    _mark_operations_action_failed,
    _mark_operations_action_succeeded,
)
from crxzipple.modules.operations.interfaces.http_action_payloads import (
    _tool_run_action_response,
)
from crxzipple.modules.operations.interfaces.http_action_service import (
    operations_action_service,
)
from crxzipple.modules.operations.interfaces.http_models import (
    OperationsActionReasonRequest,
    OperationsToolRunActionResponse,
    OperationsToolWorkerPruneRequest,
    OperationsToolWorkerPruneResponse,
)
from crxzipple.modules.tool.domain.exceptions import (
    ToolRunNotFoundError,
    ToolValidationError,
)
from crxzipple.shared.time import format_datetime_utc

router = APIRouter()


@router.post(
    "/tool/runs/{run_id}/cancel",
    response_model=OperationsToolRunActionResponse,
)
def cancel_tool_run_from_operations(
    run_id: str,
    request: OperationsActionReasonRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OperationsToolRunActionResponse:
    reason, audit_id = _begin_operations_action_audit(
        container,
        request,
        action_type="tool.run.cancel",
        target_type="tool_run",
        target_id=run_id,
        target={"run_id": run_id},
        default_reason="Operations tool run cancellation",
        risk="controlled",
    )
    try:
        run = operations_action_service(container).cancel_tool_run(
            run_id=run_id,
            reason=reason,
        )
    except ToolRunNotFoundError as exc:
        http_exc = HTTPException(status_code=404, detail=str(exc))
        _mark_operations_action_failed(container, audit_id, http_exc)
        raise http_exc from None
    except Exception as exc:
        _mark_operations_action_failed(container, audit_id, exc)
        raise
    response = _tool_run_action_response(run)
    _mark_operations_action_succeeded(container, audit_id, response)
    return response


@router.post(
    "/tool/runs/{run_id}/retry",
    response_model=OperationsToolRunActionResponse,
)
async def retry_tool_run_from_operations(
    run_id: str,
    request: OperationsActionReasonRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OperationsToolRunActionResponse:
    reason, audit_id = _begin_operations_action_audit(
        container,
        request,
        action_type="tool.run.retry",
        target_type="tool_run",
        target_id=run_id,
        target={"run_id": run_id},
        default_reason="Operations tool run retry",
        risk="controlled",
    )
    try:
        original = container.require(AppKey.TOOL_QUERY_SERVICE).get_tool_run(run_id)
        authorize_tool_run(
            container,
            tool_id=original.tool_id,
            mode=original.target.mode,
            strategy=original.target.strategy,
            environment=original.target.environment,
            interface_name="http",
            arguments=original.input_payload,
        )
        run = await operations_action_service(container).retry_tool_run(
            run_id=run_id,
            reason=reason,
        )
    except ToolRunNotFoundError as exc:
        http_exc = HTTPException(status_code=404, detail=str(exc))
        _mark_operations_action_failed(container, audit_id, http_exc)
        raise http_exc from None
    except ToolValidationError as exc:
        http_exc = HTTPException(status_code=400, detail=str(exc))
        _mark_operations_action_failed(container, audit_id, http_exc)
        raise http_exc from None
    except Exception as exc:
        _mark_operations_action_failed(container, audit_id, exc)
        raise
    response = _tool_run_action_response(run)
    _mark_operations_action_succeeded(container, audit_id, response)
    return response


@router.post(
    "/tool/workers/prune-expired",
    response_model=OperationsToolWorkerPruneResponse,
)
def prune_expired_tool_workers_from_operations(
    request: OperationsToolWorkerPruneRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OperationsToolWorkerPruneResponse:
    reason, audit_id = _begin_operations_action_audit(
        container,
        request,
        action_type="tool.workers.prune_expired",
        target_type="tool_workers",
        target={"retention_seconds": request.retention_seconds},
        default_reason="Operations prune expired tool workers",
        risk="controlled",
    )
    try:
        result = operations_action_service(container).prune_expired_tool_workers(
            retention_seconds=request.retention_seconds,
            reason=reason,
        )
    except Exception as exc:
        _mark_operations_action_failed(container, audit_id, exc)
        raise
    response = OperationsToolWorkerPruneResponse(
        pruned_count=int(result["pruned_count"]),
        worker_ids=[str(item) for item in result["worker_ids"]],
        cutoff=format_datetime_utc(result["cutoff"]),
    )
    _mark_operations_action_succeeded(container, audit_id, response)
    return response
