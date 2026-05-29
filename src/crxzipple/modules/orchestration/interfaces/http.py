from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.orchestration.application.ports import (
    OrchestrationExecutorControlPort,
    OrchestrationRunQueryPort,
    OrchestrationSchedulerMaintenancePort,
    OrchestrationSubmissionPort,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationRunNotFoundError,
    OrchestrationRunStatus,
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.interfaces.dto import OrchestrationRunDTO
from crxzipple.modules.orchestration.interfaces.http_models import (
    AdvanceAssignmentRequest,
    AssignmentWorkerRequest,
    ClaimNextAssignmentRequest,
    CompleteAssignmentRequest,
    FailAssignmentRequest,
    HeartbeatAssignmentRequest,
    IntakeOrchestrationRunRequest,
    OrchestrationRunResponse,
    RequestDueHeartbeatsRequest,
    ResumeRunRequest,
    WaitAssignmentOnToolRequest,
)


router = APIRouter()


def _bad_request(exc: OrchestrationValidationError) -> HTTPException:
    if exc.has_payload:
        return HTTPException(status_code=400, detail=exc.to_payload())
    return HTTPException(status_code=400, detail=str(exc))


def _not_found(exc: OrchestrationRunNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


def _run_query_port(container: AppContainer) -> OrchestrationRunQueryPort:
    return container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE)


def _submission_port(container: AppContainer) -> OrchestrationSubmissionPort:
    return container.require(AppKey.ORCHESTRATION_SUBMISSION_SERVICE)


def _scheduler_maintenance_port(
    container: AppContainer,
) -> OrchestrationSchedulerMaintenancePort:
    return container.require(AppKey.ORCHESTRATION_SCHEDULER_MAINTENANCE_SERVICE)


def _executor_port(container: AppContainer) -> OrchestrationExecutorControlPort:
    return container.require(AppKey.ORCHESTRATION_EXECUTOR_CONTROL_SERVICE)


@router.post(
    "/runs/intake",
    response_model=OrchestrationRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def intake_run(
    payload: IntakeOrchestrationRunRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OrchestrationRunResponse:
    submission_service = _submission_port(container)
    try:
        run = submission_service.submit_turn(
            payload.to_submit_input(),
            inline_worker_id=(
                f"http-intake:{payload.run_id or uuid4().hex}"
                if payload.enqueue
                else None
            ),
        )
    except OrchestrationValidationError as exc:
        raise _bad_request(exc) from None
    return OrchestrationRunResponse.from_dto(OrchestrationRunDTO.from_entity(run))


@router.post(
    "/executor/process-next-assigned-assignment",
    response_model=OrchestrationRunResponse | None,
)
def process_next_assigned_assignment(
    payload: ClaimNextAssignmentRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OrchestrationRunResponse | None:
    executor_service = _executor_port(container)
    try:
        run = executor_service.process_next_assigned_assignment(
            worker_id=payload.worker_id,
        )
    except OrchestrationValidationError as exc:
        raise _bad_request(exc) from None
    if run is None:
        return None
    return OrchestrationRunResponse.from_dto(OrchestrationRunDTO.from_entity(run))


@router.post(
    "/executor/runs/{run_id}/admit-assignment",
    response_model=OrchestrationRunResponse,
)
def admit_assignment(
    run_id: str,
    payload: AssignmentWorkerRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OrchestrationRunResponse:
    executor_service = _executor_port(container)
    try:
        run = executor_service.admit_assignment(
            run_id=run_id,
            worker_id=payload.worker_id,
        )
    except OrchestrationRunNotFoundError as exc:
        raise _not_found(exc) from None
    except OrchestrationValidationError as exc:
        raise _bad_request(exc) from None
    return OrchestrationRunResponse.from_dto(OrchestrationRunDTO.from_entity(run))


@router.post(
    "/executor/runs/{run_id}/process-assignment-inline",
    response_model=OrchestrationRunResponse,
)
def process_assignment_inline(
    run_id: str,
    payload: AssignmentWorkerRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OrchestrationRunResponse:
    executor_service = _executor_port(container)
    try:
        run = executor_service.process_assignment_inline(
            run_id=run_id,
            worker_id=payload.worker_id,
        )
    except OrchestrationRunNotFoundError as exc:
        raise _not_found(exc) from None
    except OrchestrationValidationError as exc:
        raise _bad_request(exc) from None
    return OrchestrationRunResponse.from_dto(OrchestrationRunDTO.from_entity(run))


@router.post(
    "/scheduler/recover-abandoned",
    response_model=list[OrchestrationRunResponse],
)
def recover_abandoned_runs(
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[OrchestrationRunResponse]:
    scheduler_service = _scheduler_maintenance_port(container)
    return [
        OrchestrationRunResponse.from_dto(OrchestrationRunDTO.from_entity(run))
        for run in scheduler_service.recover_abandoned_runs()
    ]


@router.get("/runs", response_model=list[OrchestrationRunResponse])
def list_runs(
    container: Annotated[AppContainer, Depends(get_container)],
    status: Annotated[OrchestrationRunStatus | None, Query()] = None,
) -> list[OrchestrationRunResponse]:
    run_query = _run_query_port(container)
    return [
        OrchestrationRunResponse.from_dto(OrchestrationRunDTO.from_entity(run))
        for run in run_query.list_runs(status=status)
    ]


@router.get("/runs/{run_id}", response_model=OrchestrationRunResponse)
def get_run(
    run_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OrchestrationRunResponse:
    run_query = _run_query_port(container)
    try:
        run = run_query.get_run(run_id)
    except OrchestrationRunNotFoundError as exc:
        raise _not_found(exc) from None
    return OrchestrationRunResponse.from_dto(OrchestrationRunDTO.from_entity(run))


@router.post(
    "/executor/runs/{run_id}/advance-assignment",
    response_model=OrchestrationRunResponse,
)
def advance_assignment(
    run_id: str,
    payload: AdvanceAssignmentRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OrchestrationRunResponse:
    executor_service = _executor_port(container)
    try:
        request = payload.to_input(run_id=run_id)
        run = executor_service.advance_assignment(
            run_id=request.run_id,
            worker_id=request.worker_id,
            stage=request.stage,
            step_increment=request.step_increment,
            metadata=request.metadata,
        )
    except OrchestrationRunNotFoundError as exc:
        raise _not_found(exc) from None
    except OrchestrationValidationError as exc:
        raise _bad_request(exc) from None
    return OrchestrationRunResponse.from_dto(OrchestrationRunDTO.from_entity(run))


@router.post(
    "/executor/runs/{run_id}/heartbeat-assignment",
    response_model=OrchestrationRunResponse,
)
def heartbeat_assignment(
    run_id: str,
    payload: HeartbeatAssignmentRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OrchestrationRunResponse:
    executor_service = _executor_port(container)
    try:
        run = executor_service.heartbeat_assignment(
            run_id=run_id,
            worker_id=payload.worker_id,
        )
    except OrchestrationRunNotFoundError as exc:
        raise _not_found(exc) from None
    except OrchestrationValidationError as exc:
        raise _bad_request(exc) from None
    return OrchestrationRunResponse.from_dto(OrchestrationRunDTO.from_entity(run))


@router.post(
    "/heartbeats/request-due",
    response_model=list[OrchestrationRunResponse],
)
def request_due_heartbeats(
    payload: RequestDueHeartbeatsRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[OrchestrationRunResponse]:
    scheduler_service = _scheduler_maintenance_port(container)
    try:
        runs = scheduler_service.request_due_heartbeats(
            payload.to_input(),
        )
    except OrchestrationValidationError as exc:
        raise _bad_request(exc) from None
    return [
        OrchestrationRunResponse.from_dto(OrchestrationRunDTO.from_entity(run))
        for run in runs
    ]


@router.post(
    "/executor/runs/{run_id}/wait-assignment-on-tool",
    response_model=OrchestrationRunResponse,
)
def wait_assignment_on_tool(
    run_id: str,
    payload: WaitAssignmentOnToolRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OrchestrationRunResponse:
    executor_service = _executor_port(container)
    try:
        request = payload.to_input(run_id=run_id)
        run = executor_service.wait_assignment_on_tool(
            run_id=request.run_id,
            worker_id=request.worker_id,
            pending_tool_run_ids=request.pending_tool_run_ids,
            reason=request.reason,
        )
    except OrchestrationRunNotFoundError as exc:
        raise _not_found(exc) from None
    except OrchestrationValidationError as exc:
        raise _bad_request(exc) from None
    return OrchestrationRunResponse.from_dto(OrchestrationRunDTO.from_entity(run))


@router.post("/runs/{run_id}/resume", response_model=OrchestrationRunResponse)
def resume_run(
    run_id: str,
    payload: ResumeRunRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OrchestrationRunResponse:
    scheduler_service = _scheduler_maintenance_port(container)
    try:
        request = payload.to_input(run_id=run_id)
        run = scheduler_service.resume_run(
            request,
        )
    except OrchestrationRunNotFoundError as exc:
        raise _not_found(exc) from None
    except OrchestrationValidationError as exc:
        raise _bad_request(exc) from None
    return OrchestrationRunResponse.from_dto(OrchestrationRunDTO.from_entity(run))


@router.post(
    "/executor/runs/{run_id}/complete-assignment",
    response_model=OrchestrationRunResponse,
)
def complete_assignment(
    run_id: str,
    payload: CompleteAssignmentRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OrchestrationRunResponse:
    executor_service = _executor_port(container)
    try:
        request = payload.to_input(run_id=run_id)
        run = executor_service.complete_assignment(
            run_id=request.run_id,
            worker_id=request.worker_id,
            result_payload=request.result_payload,
        )
    except OrchestrationRunNotFoundError as exc:
        raise _not_found(exc) from None
    except OrchestrationValidationError as exc:
        raise _bad_request(exc) from None
    return OrchestrationRunResponse.from_dto(OrchestrationRunDTO.from_entity(run))


@router.post(
    "/executor/runs/{run_id}/fail-assignment",
    response_model=OrchestrationRunResponse,
)
def fail_assignment(
    run_id: str,
    payload: FailAssignmentRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OrchestrationRunResponse:
    executor_service = _executor_port(container)
    try:
        request = payload.to_input(run_id=run_id)
        run = executor_service.fail_assignment(
            run_id=request.run_id,
            message=request.message,
            code=request.code,
            details=request.details,
            worker_id=request.worker_id,
        )
    except OrchestrationRunNotFoundError as exc:
        raise _not_found(exc) from None
    except OrchestrationValidationError as exc:
        raise _bad_request(exc) from None
    return OrchestrationRunResponse.from_dto(OrchestrationRunDTO.from_entity(run))
