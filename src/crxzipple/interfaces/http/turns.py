from __future__ import annotations

from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.modules.orchestration.application import (
    RequestCompactionInput,
    RequestHeartbeatInput,
    RequestMemoryFlushInput,
    ResolveApprovalRequestInput,
    SubmitBoundOrchestrationTurnInput,
)
from crxzipple.modules.orchestration.application.turn_submission import (
    build_accept_run_input,
    build_submission_options,
    runtime_request_bootstrap_metadata_for_content,
    resolve_profile,
    submit_turn,
)
from crxzipple.modules.orchestration.domain import (
    ApprovalDecision,
    OrchestrationRunNotFoundError,
    OrchestrationQueuePolicy,
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.application.ports import (
    OrchestrationApprovalControlPort,
    OrchestrationCancellationPort,
    OrchestrationExecutorProcessPort,
    OrchestrationInspectionPort,
    OrchestrationRunLookupPort,
    OrchestrationSchedulerMaintenancePort,
    OrchestrationSubmissionPort,
)
from crxzipple.modules.orchestration.interfaces.dto import (
    OrchestrationRunDTO,
    RuntimeLlmRequestPreviewDTO,
)
from crxzipple.modules.orchestration.interfaces.http_models import OrchestrationRunResponse
from crxzipple.modules.session.domain import DirectSessionScope
from crxzipple.modules.session.domain.exceptions import SessionNotFoundError


router = APIRouter()


class CreateTurnRequest(BaseModel):
    content: Any
    agent_id: str | None = None
    llm_id: str | None = None
    session_key: str | None = None
    new_session: bool = False
    channel: str = "crxzipple"
    chat_type: str = "direct"
    peer_id: str | None = None
    conversation_id: str | None = None
    thread_id: str | None = None
    account_id: str | None = None
    main_key: str | None = None
    direct_scope: DirectSessionScope = DirectSessionScope.MAIN
    source: str = "http"
    queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.JUMP_QUEUE
    priority: int = Field(default=100, ge=0)
    max_steps: int | None = Field(default=None, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TurnResponse(BaseModel):
    run: OrchestrationRunResponse
    output_text: str | None = None

    @classmethod
    def from_entity(cls, dto: OrchestrationRunDTO) -> "TurnResponse":
        return cls(
            run=OrchestrationRunResponse.from_dto(dto),
            output_text=(
                dto.result_payload.get("output_text")
                if dto.result_payload is not None
                and isinstance(dto.result_payload.get("output_text"), str)
                else None
            ),
        )


class RuntimeLlmRequestPreviewMessageResponse(BaseModel):
    role: str
    content: Any
    name: str | None = None
    tool_call_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeLlmRequestPreviewToolSchemaResponse(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class RuntimeLlmRequestPreviewResponse(BaseModel):
    run_id: str
    llm_id: str
    mode: str
    messages: list[RuntimeLlmRequestPreviewMessageResponse] = Field(default_factory=list)
    input_items: list[dict[str, Any]] = Field(default_factory=list)
    tool_schemas: list[RuntimeLlmRequestPreviewToolSchemaResponse] = Field(default_factory=list)
    runtime_request_report: dict[str, Any] | None = None
    request_render_snapshot_id: str | None = None
    request_render_snapshot: dict[str, Any] | None = None
    request_render_snapshot_metadata: dict[str, Any] = Field(default_factory=dict)
    tool_surface: dict[str, Any] = Field(default_factory=dict)
    runtime_context: dict[str, Any] = Field(default_factory=dict)
    provider_request_options: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_dto(cls, dto: RuntimeLlmRequestPreviewDTO) -> "RuntimeLlmRequestPreviewResponse":
        return cls(
            run_id=dto.run_id,
            llm_id=dto.llm_id,
            mode=dto.mode,
            messages=[
                RuntimeLlmRequestPreviewMessageResponse(
                    role=item.role,
                    content=item.content,
                    name=item.name,
                    tool_call_id=item.tool_call_id,
                    metadata=dict(item.metadata),
                )
                for item in dto.messages
            ],
            input_items=[dict(item) for item in dto.input_items],
            tool_schemas=[
                RuntimeLlmRequestPreviewToolSchemaResponse(
                    name=item.name,
                    description=item.description,
                    input_schema=dict(item.input_schema),
                )
                for item in dto.tool_schemas
            ],
            runtime_request_report=(
                dict(dto.runtime_request_report)
                if dto.runtime_request_report is not None
                else None
            ),
            request_render_snapshot_id=dto.request_render_snapshot_id,
            request_render_snapshot=(
                dict(dto.request_render_snapshot)
                if dto.request_render_snapshot is not None
                else None
            ),
            request_render_snapshot_metadata=dict(dto.request_render_snapshot_metadata),
            tool_surface=dict(dto.tool_surface),
            runtime_context=dict(dto.runtime_context),
            provider_request_options=dict(dto.provider_request_options),
        )


class CancelTurnRequest(BaseModel):
    reason: str | None = None


class ResolveApprovalRequestRequest(BaseModel):
    decision: ApprovalDecision


class RequestCompactionRequest(BaseModel):
    reason: str | None = None
    preserve: str | None = None
    queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.JUMP_QUEUE
    priority: int | None = Field(default=None, ge=0)
    max_steps: int = Field(default=1, ge=1)


class RequestHeartbeatRequest(BaseModel):
    reason: str | None = None
    idle_reply: str | None = "HEARTBEAT_OK"
    queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.JUMP_QUEUE
    priority: int | None = Field(default=None, ge=0)
    max_steps: int = Field(default=1, ge=1)


class RequestMemoryFlushRequest(BaseModel):
    reason: str | None = None
    queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.JUMP_QUEUE
    priority: int | None = Field(default=None, ge=0)
    max_steps: int = Field(default=1, ge=1)


def _turn_response_from_run(run) -> TurnResponse:  # noqa: ANN001
    return TurnResponse.from_entity(OrchestrationRunDTO.from_entity(run))


def _inspection_port(container: AppContainer) -> OrchestrationInspectionPort:
    return container.require(AppKey.ORCHESTRATION_INSPECTION_SERVICE)


def _approval_control_port(
    container: AppContainer,
) -> OrchestrationApprovalControlPort:
    return container.require(AppKey.ORCHESTRATION_APPROVAL_CONTROL_SERVICE)


def _cancellation_port(container: AppContainer) -> OrchestrationCancellationPort:
    return container.require(AppKey.ORCHESTRATION_CANCELLATION_SERVICE)


def _run_lookup_port(container: AppContainer) -> OrchestrationRunLookupPort:
    return container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE)


def _submission_port(container: AppContainer) -> OrchestrationSubmissionPort:
    return container.require(AppKey.ORCHESTRATION_SUBMISSION_SERVICE)


def _scheduler_maintenance_port(
    container: AppContainer,
) -> OrchestrationSchedulerMaintenancePort:
    return container.require(AppKey.ORCHESTRATION_SCHEDULER_MAINTENANCE_SERVICE)


def _executor_process_port(container: AppContainer) -> OrchestrationExecutorProcessPort:
    return container.require(AppKey.ORCHESTRATION_EXECUTOR_CONTROL_SERVICE)


def _trimmed(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _main_key_for_payload(payload: CreateTurnRequest) -> str:
    if payload.new_session:
        return f"conversation:{uuid4().hex}"
    return _trimmed(payload.main_key) or "main"


@router.post(
    "/turns",
    response_model=TurnResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_turn(
    payload: CreateTurnRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> TurnResponse:
    session_key = _trimmed(payload.session_key)
    if session_key is not None and payload.new_session:
        raise HTTPException(
            status_code=400,
            detail="session_key and new_session cannot be used together.",
        )
    try:
        target_session = (
            container.require(AppKey.SESSION_SERVICE).get_session(session_key)
            if session_key is not None
            else None
        )
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None

    target_binding = (
        target_session.runtime_binding() if target_session is not None else None
    )
    requested_agent_id = _trimmed(payload.agent_id)
    target_agent_id = (
        requested_agent_id
        if requested_agent_id is not None
        else target_binding.agent_id if target_binding is not None else None
    )
    profile, error = resolve_profile(
        container.require(AppKey.AGENT_SERVICE),
        agent_id=target_agent_id,
    )
    if profile is None:
        raise HTTPException(status_code=404, detail=error or "Agent profile was not found.")

    options = build_submission_options(
        profile=profile,
        llm_id=payload.llm_id,
        channel=payload.channel,
        chat_type=payload.chat_type,
        peer_id=payload.peer_id,
        conversation_id=payload.conversation_id,
        thread_id=payload.thread_id,
        account_id=payload.account_id,
        main_key=_main_key_for_payload(payload),
        direct_scope=payload.direct_scope,
        source=payload.source,
        queue_policy=payload.queue_policy,
        priority=payload.priority,
        max_steps=payload.max_steps,
    )

    try:
        submission_service = _submission_port(container)
        submission_metadata = runtime_request_bootstrap_metadata_for_content(
            payload.content,
            metadata=payload.metadata,
        )
        if target_session is None:
            run = submit_turn(
                submission_service,
                content=payload.content,
                options=options,
                inline_worker_id=None,
                metadata=submission_metadata,
            )
        else:
            if (
                target_binding is not None
                and target_binding.agent_id is not None
                and target_binding.agent_id != profile.id
            ):
                raise OrchestrationValidationError(
                    "Submitted agent does not match the target session owner.",
                )
            run = submission_service.submit_bound_turn(
                SubmitBoundOrchestrationTurnInput(
                    accept_input=build_accept_run_input(
                        source=options.source,
                        content=payload.content,
                        queue_policy=options.queue_policy,
                        priority=options.priority,
                        max_steps=options.max_steps,
                        metadata=submission_metadata,
                    ),
                    agent_id=profile.id,
                    session_key=target_session.id,
                    active_session_id=target_session.active_session_id,
                    requested_llm_id=options.llm_id,
                    metadata=submission_metadata,
                    enqueue_queue_policy=options.queue_policy,
                    enqueue_priority=options.priority,
                ),
                inline_worker_id=None,
            )
    except OrchestrationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    return _turn_response_from_run(run)


@router.get("/turns/{run_id}", response_model=TurnResponse)
def get_turn(
    run_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> TurnResponse:
    run_lookup = _run_lookup_port(container)
    try:
        run = run_lookup.get_run(run_id)
    except OrchestrationRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return _turn_response_from_run(run)


@router.get("/turns/{run_id}/llm-request-preview", response_model=RuntimeLlmRequestPreviewResponse)
def get_turn_llm_request_preview(
    run_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> RuntimeLlmRequestPreviewResponse:
    inspection_service = _inspection_port(container)
    try:
        preview = inspection_service.preview_runtime_llm_request(run_id)
    except OrchestrationRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except OrchestrationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return RuntimeLlmRequestPreviewResponse.from_dto(
        RuntimeLlmRequestPreviewDTO.from_value(
            run_id=run_id,
            preview=preview,
        ),
    )


@router.post("/turns/{run_id}/cancel", response_model=TurnResponse)
def cancel_turn(
    run_id: str,
    payload: CancelTurnRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> TurnResponse:
    cancellation_service = _cancellation_port(container)
    try:
        run = cancellation_service.cancel_run(
            run_id,
            reason=payload.reason,
        )
    except OrchestrationRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except OrchestrationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _turn_response_from_run(run)


@router.post(
    "/turns/{run_id}/compact",
    response_model=TurnResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_turn_compaction(
    run_id: str,
    payload: RequestCompactionRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> TurnResponse:
    scheduler_service = _scheduler_maintenance_port(container)
    try:
        run = scheduler_service.request_compaction(
            RequestCompactionInput(
                anchor_run_id=run_id,
                reason=payload.reason,
                preserve=payload.preserve,
                queue_policy=payload.queue_policy,
                priority=payload.priority,
                max_steps=payload.max_steps,
            ),
        )
    except OrchestrationRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except OrchestrationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _turn_response_from_run(run)


@router.post(
    "/turns/{run_id}/heartbeat",
    response_model=TurnResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_turn_heartbeat(
    run_id: str,
    payload: RequestHeartbeatRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> TurnResponse:
    scheduler_service = _scheduler_maintenance_port(container)
    try:
        run = scheduler_service.request_heartbeat(
            RequestHeartbeatInput(
                anchor_run_id=run_id,
                reason=payload.reason,
                idle_reply=payload.idle_reply,
                queue_policy=payload.queue_policy,
                priority=payload.priority,
                max_steps=payload.max_steps,
            ),
        )
    except OrchestrationRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except OrchestrationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _turn_response_from_run(run)


@router.post(
    "/turns/{run_id}/memory-flush",
    response_model=TurnResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_turn_memory_flush(
    run_id: str,
    payload: RequestMemoryFlushRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> TurnResponse:
    scheduler_service = _scheduler_maintenance_port(container)
    try:
        run = scheduler_service.request_memory_flush(
            RequestMemoryFlushInput(
                anchor_run_id=run_id,
                reason=payload.reason,
                queue_policy=payload.queue_policy,
                priority=payload.priority,
                max_steps=payload.max_steps,
            ),
        )
    except OrchestrationRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except OrchestrationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _turn_response_from_run(run)


@router.post(
    "/turns/{run_id}/approvals/{request_id}",
    response_model=TurnResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def resolve_turn_approval(
    run_id: str,
    request_id: str,
    payload: ResolveApprovalRequestRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> TurnResponse:
    approval_control_service = _approval_control_port(container)
    try:
        run = approval_control_service.resolve_approval_request(
            ResolveApprovalRequestInput(
                run_id=run_id,
                request_id=request_id,
                decision=payload.decision,
            ),
        )
        if run.status.value == "queued":
            executor_service = _executor_process_port(container)
            processed = executor_service.process_assignment_inline(
                run_id=run.id,
                worker_id=f"http-approval:{run.id}",
            )
            if processed.id == run.id:
                run = processed
    except OrchestrationRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except OrchestrationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _turn_response_from_run(run)
