from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.dispatch.application import (
    CancelDispatchTaskInput,
    CompleteDispatchTaskInput,
    CreateDispatchTaskInput,
    EnqueueDispatchTaskInput,
    FailDispatchTaskInput,
    HeartbeatDispatchTaskInput,
    RequeueDispatchTaskInput,
    RecoverAbandonedDispatchTasksInput,
    WaitDispatchTaskInput,
)
from crxzipple.modules.dispatch.domain import (
    DispatchPolicy,
    DispatchTaskNotFoundError,
    DispatchTaskStatus,
    DispatchValidationError,
)
from crxzipple.modules.dispatch.interfaces.dto import DispatchTaskDTO


router = APIRouter()


class DispatchTaskRequest(BaseModel):
    owner_kind: str
    owner_id: str
    lane_key: str | None = None
    task_id: str | None = None
    policy: DispatchPolicy = DispatchPolicy.FIFO
    priority: int = Field(default=100, ge=0)
    payload_ref: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class DispatchTaskUpdateRequest(BaseModel):
    lane_key: str | None = None
    policy: DispatchPolicy | None = None
    priority: int | None = Field(default=None, ge=0)


class ClaimNextDispatchTaskRequest(BaseModel):
    owner_kind: str | None = None
    worker_id: str
    claim_token: str | None = None
    lease_seconds: int | None = Field(default=None, gt=0)


class WaitDispatchTaskRequest(BaseModel):
    reason: str | None = None


class HeartbeatDispatchTaskRequest(BaseModel):
    worker_id: str
    lease_seconds: int = Field(..., gt=0)
    claim_token: str | None = None


class RequeueDispatchTaskRequest(BaseModel):
    policy: DispatchPolicy | None = None
    priority: int | None = Field(default=None, ge=0)
    reason: str | None = None


class CancelDispatchTaskRequest(BaseModel):
    reason: str | None = None


class FailDispatchTaskRequest(BaseModel):
    message: str
    code: str = "dispatch_failed"
    details: dict[str, object] = Field(default_factory=dict)


class RecoverAbandonedDispatchTasksRequest(BaseModel):
    owner_kind: str | None = None
    reason: str = "Dispatch worker lease expired before completion."


class DispatchErrorResponse(BaseModel):
    message: str
    code: str
    details: dict[str, object] = Field(default_factory=dict)


class DispatchTaskResponse(BaseModel):
    id: str
    owner_kind: str
    owner_id: str
    lane_key: str | None = None
    status: str
    policy: str
    priority: int
    payload_ref: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    waiting_reason: str | None = None
    error: DispatchErrorResponse | None = None
    claimed_by: str | None = None
    claim_token: str | None = None
    created_at: str
    updated_at: str
    queued_at: str | None = None
    claimed_at: str | None = None
    heartbeat_at: str | None = None
    lease_expires_at: str | None = None
    completed_at: str | None = None


def _to_response(dto: DispatchTaskDTO) -> DispatchTaskResponse:
    return DispatchTaskResponse(
        id=dto.id,
        owner_kind=dto.owner_kind,
        owner_id=dto.owner_id,
        lane_key=dto.lane_key,
        status=dto.status,
        policy=dto.policy,
        priority=dto.priority,
        payload_ref=dto.payload_ref,
        metadata=dto.metadata,
        waiting_reason=dto.waiting_reason,
        error=(
            DispatchErrorResponse(
                message=dto.error.message,
                code=dto.error.code,
                details=dto.error.details,
            )
            if dto.error is not None
            else None
        ),
        claimed_by=dto.claimed_by,
        claim_token=dto.claim_token,
        created_at=dto.created_at.isoformat(),
        updated_at=dto.updated_at.isoformat(),
        queued_at=dto.queued_at.isoformat() if dto.queued_at is not None else None,
        claimed_at=dto.claimed_at.isoformat() if dto.claimed_at is not None else None,
        heartbeat_at=(
            dto.heartbeat_at.isoformat() if dto.heartbeat_at is not None else None
        ),
        lease_expires_at=(
            dto.lease_expires_at.isoformat()
            if dto.lease_expires_at is not None
            else None
        ),
        completed_at=(
            dto.completed_at.isoformat() if dto.completed_at is not None else None
        ),
    )


def _bad_request(exc: DispatchValidationError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _not_found(exc: DispatchTaskNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


@router.post("/tasks", response_model=DispatchTaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: DispatchTaskRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> DispatchTaskResponse:
    try:
        task = container.require(AppKey.DISPATCH_SERVICE).create_task(
            CreateDispatchTaskInput(
                task_id=payload.task_id,
                owner_kind=payload.owner_kind,
                owner_id=payload.owner_id,
                lane_key=payload.lane_key,
                policy=payload.policy,
                priority=payload.priority,
                payload_ref=payload.payload_ref,
                metadata=payload.metadata,
            ),
        )
    except DispatchValidationError as exc:
        raise _bad_request(exc) from exc
    return _to_response(DispatchTaskDTO.from_entity(task))


@router.get("/tasks/{task_id}", response_model=DispatchTaskResponse)
def get_task(
    task_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> DispatchTaskResponse:
    try:
        task = container.require(AppKey.DISPATCH_SERVICE).get_task(task_id)
    except DispatchTaskNotFoundError as exc:
        raise _not_found(exc) from exc
    return _to_response(DispatchTaskDTO.from_entity(task))


@router.get("/tasks", response_model=list[DispatchTaskResponse])
def list_tasks(
    container: Annotated[AppContainer, Depends(get_container)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    owner_kind: str | None = None,
    lane_key: str | None = None,
) -> list[DispatchTaskResponse]:
    try:
        resolved_status = (
            DispatchTaskStatus(status_filter) if status_filter is not None else None
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    items = [
        _to_response(DispatchTaskDTO.from_entity(task))
        for task in container.require(AppKey.DISPATCH_SERVICE).list_tasks(
            status=resolved_status,
            owner_kind=owner_kind,
            lane_key=lane_key,
        )
    ]
    return items


@router.post("/tasks/{task_id}/enqueue", response_model=DispatchTaskResponse)
def enqueue_task(
    task_id: str,
    payload: DispatchTaskUpdateRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> DispatchTaskResponse:
    try:
        task = container.require(AppKey.DISPATCH_SERVICE).enqueue_task(
            EnqueueDispatchTaskInput(
                task_id=task_id,
                lane_key=payload.lane_key,
                policy=payload.policy,
                priority=payload.priority,
            ),
        )
    except DispatchTaskNotFoundError as exc:
        raise _not_found(exc) from exc
    except DispatchValidationError as exc:
        raise _bad_request(exc) from exc
    return _to_response(DispatchTaskDTO.from_entity(task))


@router.post("/tasks/claim-next", response_model=DispatchTaskResponse | None)
def claim_next_task(
    payload: ClaimNextDispatchTaskRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> DispatchTaskResponse | None:
    try:
        task = container.require(AppKey.DISPATCH_SERVICE).claim_next_queued_task(
            owner_kind=payload.owner_kind,
            worker_id=payload.worker_id,
            claim_token=payload.claim_token,
            lease_seconds=payload.lease_seconds,
        )
    except DispatchValidationError as exc:
        raise _bad_request(exc) from exc
    if task is None:
        return None
    return _to_response(DispatchTaskDTO.from_entity(task))


@router.post("/tasks/{task_id}/wait", response_model=DispatchTaskResponse)
def wait_task(
    task_id: str,
    payload: WaitDispatchTaskRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> DispatchTaskResponse:
    try:
        task = container.require(AppKey.DISPATCH_SERVICE).wait_task(
            WaitDispatchTaskInput(
                task_id=task_id,
                reason=payload.reason,
            ),
        )
    except DispatchTaskNotFoundError as exc:
        raise _not_found(exc) from exc
    except DispatchValidationError as exc:
        raise _bad_request(exc) from exc
    return _to_response(DispatchTaskDTO.from_entity(task))


@router.post("/tasks/{task_id}/heartbeat", response_model=DispatchTaskResponse)
def heartbeat_task(
    task_id: str,
    payload: HeartbeatDispatchTaskRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> DispatchTaskResponse:
    try:
        task = container.require(AppKey.DISPATCH_SERVICE).heartbeat_task(
            HeartbeatDispatchTaskInput(
                task_id=task_id,
                worker_id=payload.worker_id,
                lease_seconds=payload.lease_seconds,
                claim_token=payload.claim_token,
            ),
        )
    except DispatchTaskNotFoundError as exc:
        raise _not_found(exc) from exc
    except DispatchValidationError as exc:
        raise _bad_request(exc) from exc
    return _to_response(DispatchTaskDTO.from_entity(task))


@router.post("/tasks/{task_id}/requeue", response_model=DispatchTaskResponse)
def requeue_task(
    task_id: str,
    payload: RequeueDispatchTaskRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> DispatchTaskResponse:
    try:
        task = container.require(AppKey.DISPATCH_SERVICE).requeue_task(
            RequeueDispatchTaskInput(
                task_id=task_id,
                policy=payload.policy,
                priority=payload.priority,
                reason=payload.reason,
            ),
        )
    except DispatchTaskNotFoundError as exc:
        raise _not_found(exc) from exc
    except DispatchValidationError as exc:
        raise _bad_request(exc) from exc
    return _to_response(DispatchTaskDTO.from_entity(task))


@router.post("/tasks/recover-abandoned", response_model=list[DispatchTaskResponse])
def recover_abandoned_tasks(
    payload: RecoverAbandonedDispatchTasksRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[DispatchTaskResponse]:
    try:
        tasks = container.require(AppKey.DISPATCH_SERVICE).recover_abandoned_tasks(
            RecoverAbandonedDispatchTasksInput(
                owner_kind=payload.owner_kind,
                reason=payload.reason,
            ),
        )
    except DispatchValidationError as exc:
        raise _bad_request(exc) from exc
    return [_to_response(DispatchTaskDTO.from_entity(task)) for task in tasks]


@router.post("/tasks/{task_id}/complete", response_model=DispatchTaskResponse)
def complete_task(
    task_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> DispatchTaskResponse:
    try:
        task = container.require(AppKey.DISPATCH_SERVICE).complete_task(
            CompleteDispatchTaskInput(task_id=task_id),
        )
    except DispatchTaskNotFoundError as exc:
        raise _not_found(exc) from exc
    except DispatchValidationError as exc:
        raise _bad_request(exc) from exc
    return _to_response(DispatchTaskDTO.from_entity(task))


@router.post("/tasks/{task_id}/cancel", response_model=DispatchTaskResponse)
def cancel_task(
    task_id: str,
    payload: CancelDispatchTaskRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> DispatchTaskResponse:
    try:
        task = container.require(AppKey.DISPATCH_SERVICE).cancel_task(
            CancelDispatchTaskInput(
                task_id=task_id,
                reason=payload.reason,
            ),
        )
    except DispatchTaskNotFoundError as exc:
        raise _not_found(exc) from exc
    except DispatchValidationError as exc:
        raise _bad_request(exc) from exc
    return _to_response(DispatchTaskDTO.from_entity(task))


@router.post("/tasks/{task_id}/fail", response_model=DispatchTaskResponse)
def fail_task(
    task_id: str,
    payload: FailDispatchTaskRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> DispatchTaskResponse:
    try:
        task = container.require(AppKey.DISPATCH_SERVICE).fail_task(
            FailDispatchTaskInput(
                task_id=task_id,
                message=payload.message,
                code=payload.code,
                details=payload.details,
            ),
        )
    except DispatchTaskNotFoundError as exc:
        raise _not_found(exc) from exc
    except DispatchValidationError as exc:
        raise _bad_request(exc) from exc
    return _to_response(DispatchTaskDTO.from_entity(task))
