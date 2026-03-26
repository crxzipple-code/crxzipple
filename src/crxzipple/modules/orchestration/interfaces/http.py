from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from crxzipple.bootstrap import AppContainer
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.orchestration.domain import (
    OrchestrationRunNotFoundError,
    OrchestrationRunStatus,
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.interfaces.dto import OrchestrationRunDTO
from crxzipple.modules.orchestration.interfaces.http_models import (
    AdvanceRunRequest,
    ClaimNextRunRequest,
    CompleteRunRequest,
    FailRunRequest,
    HeartbeatRunRequest,
    IntakeOrchestrationRunRequest,
    OrchestrationRunResponse,
    RequestDueHeartbeatsRequest,
    ResumeRunRequest,
    WaitOnToolRequest,
)


router = APIRouter()


def _bad_request(exc: OrchestrationValidationError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _not_found(exc: OrchestrationRunNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


@router.post(
    "/runs/intake",
    response_model=OrchestrationRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def intake_run(
    payload: IntakeOrchestrationRunRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OrchestrationRunResponse:
    try:
        accepted = container.orchestration_service.accept(payload.to_accept_input())
        prepared = container.orchestration_service.prepare_session_run(
            payload.to_prepare_input(run_id=accepted.id),
        )
        run = prepared
        if payload.enqueue:
            run = container.orchestration_service.enqueue(
                payload.to_enqueue_input(run_id=prepared.id),
            )
    except OrchestrationValidationError as exc:
        raise _bad_request(exc) from None
    return OrchestrationRunResponse.from_dto(OrchestrationRunDTO.from_entity(run))


@router.post("/worker/claim-next", response_model=OrchestrationRunResponse | None)
def claim_next_run(
    payload: ClaimNextRunRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OrchestrationRunResponse | None:
    try:
        run = container.orchestration_service.claim_next_queued_run(
            worker_id=payload.worker_id,
        )
    except OrchestrationValidationError as exc:
        raise _bad_request(exc) from None
    if run is None:
        return None
    return OrchestrationRunResponse.from_dto(OrchestrationRunDTO.from_entity(run))


@router.post("/worker/process-next", response_model=OrchestrationRunResponse | None)
def process_next_run(
    payload: ClaimNextRunRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OrchestrationRunResponse | None:
    try:
        run = container.orchestration_service.process_next_queued_run(
            worker_id=payload.worker_id,
        )
    except OrchestrationValidationError as exc:
        raise _bad_request(exc) from None
    if run is None:
        return None
    return OrchestrationRunResponse.from_dto(OrchestrationRunDTO.from_entity(run))


@router.post(
    "/worker/recover-abandoned",
    response_model=list[OrchestrationRunResponse],
)
def recover_abandoned_runs(
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[OrchestrationRunResponse]:
    return [
        OrchestrationRunResponse.from_dto(OrchestrationRunDTO.from_entity(run))
        for run in container.orchestration_service.recover_abandoned_runs()
    ]


@router.get("/runs", response_model=list[OrchestrationRunResponse])
def list_runs(
    container: Annotated[AppContainer, Depends(get_container)],
    status: Annotated[OrchestrationRunStatus | None, Query()] = None,
) -> list[OrchestrationRunResponse]:
    return [
        OrchestrationRunResponse.from_dto(OrchestrationRunDTO.from_entity(run))
        for run in container.orchestration_service.list_runs(status=status)
    ]


@router.get("/runs/{run_id}", response_model=OrchestrationRunResponse)
def get_run(
    run_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OrchestrationRunResponse:
    try:
        run = container.orchestration_service.get_run(run_id)
    except OrchestrationRunNotFoundError as exc:
        raise _not_found(exc) from None
    return OrchestrationRunResponse.from_dto(OrchestrationRunDTO.from_entity(run))


@router.post("/runs/{run_id}/advance", response_model=OrchestrationRunResponse)
def advance_run(
    run_id: str,
    payload: AdvanceRunRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OrchestrationRunResponse:
    try:
        run = container.orchestration_service.advance_run(payload.to_input(run_id=run_id))
    except OrchestrationRunNotFoundError as exc:
        raise _not_found(exc) from None
    except OrchestrationValidationError as exc:
        raise _bad_request(exc) from None
    return OrchestrationRunResponse.from_dto(OrchestrationRunDTO.from_entity(run))


@router.post("/runs/{run_id}/heartbeat", response_model=OrchestrationRunResponse)
def heartbeat_run(
    run_id: str,
    payload: HeartbeatRunRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OrchestrationRunResponse:
    try:
        run = container.orchestration_service.heartbeat_run(
            run_id,
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
    try:
        runs = container.orchestration_service.request_due_heartbeats(
            payload.to_input(),
        )
    except OrchestrationValidationError as exc:
        raise _bad_request(exc) from None
    return [
        OrchestrationRunResponse.from_dto(OrchestrationRunDTO.from_entity(run))
        for run in runs
    ]


@router.post("/runs/{run_id}/wait-on-tool", response_model=OrchestrationRunResponse)
def wait_on_tool(
    run_id: str,
    payload: WaitOnToolRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OrchestrationRunResponse:
    try:
        run = container.orchestration_service.wait_on_tool(payload.to_input(run_id=run_id))
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
    try:
        run = container.orchestration_service.resume_run(payload.to_input(run_id=run_id))
    except OrchestrationRunNotFoundError as exc:
        raise _not_found(exc) from None
    except OrchestrationValidationError as exc:
        raise _bad_request(exc) from None
    return OrchestrationRunResponse.from_dto(OrchestrationRunDTO.from_entity(run))


@router.post("/runs/{run_id}/complete", response_model=OrchestrationRunResponse)
def complete_run(
    run_id: str,
    payload: CompleteRunRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OrchestrationRunResponse:
    try:
        run = container.orchestration_service.complete_run(payload.to_input(run_id=run_id))
    except OrchestrationRunNotFoundError as exc:
        raise _not_found(exc) from None
    except OrchestrationValidationError as exc:
        raise _bad_request(exc) from None
    return OrchestrationRunResponse.from_dto(OrchestrationRunDTO.from_entity(run))


@router.post("/runs/{run_id}/fail", response_model=OrchestrationRunResponse)
def fail_run(
    run_id: str,
    payload: FailRunRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OrchestrationRunResponse:
    try:
        run = container.orchestration_service.fail_run(payload.to_input(run_id=run_id))
    except OrchestrationRunNotFoundError as exc:
        raise _not_found(exc) from None
    except OrchestrationValidationError as exc:
        raise _bad_request(exc) from None
    return OrchestrationRunResponse.from_dto(OrchestrationRunDTO.from_entity(run))
