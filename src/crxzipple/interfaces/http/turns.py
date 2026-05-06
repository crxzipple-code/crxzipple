from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from crxzipple.bootstrap import AppContainer
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.orchestration.application.turn_submission import (
    build_submission_options,
    extract_output_text,
    resolve_profile,
    submit_turn,
)
from crxzipple.modules.orchestration.domain import (
    ApprovalDecision,
    OrchestrationRunNotFoundError,
    OrchestrationQueuePolicy,
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.application import ResolveApprovalRequestInput
from crxzipple.modules.orchestration.application import RequestCompactionInput
from crxzipple.modules.orchestration.application import RequestHeartbeatInput
from crxzipple.modules.orchestration.application import RequestMemoryFlushInput
from crxzipple.modules.orchestration.application.ports import (
    OrchestrationApprovalControlPort,
    OrchestrationCancellationPort,
    OrchestrationExecutorProcessPort,
    OrchestrationInspectionPort,
    OrchestrationRunLookupPort,
    OrchestrationSchedulerRuntimePort,
)
from crxzipple.modules.orchestration.interfaces.dto import (
    OrchestrationRunDTO,
    PromptPreviewDTO,
)
from crxzipple.modules.orchestration.interfaces.http_models import OrchestrationRunResponse
from crxzipple.modules.session.domain import DirectSessionScope


router = APIRouter()


class CreateTurnRequest(BaseModel):
    content: Any
    agent_id: str | None = None
    llm_id: str | None = None
    channel: str = "crxzipple"
    chat_type: str = "direct"
    peer_id: str | None = None
    conversation_id: str | None = None
    thread_id: str | None = None
    account_id: str | None = None
    main_key: str = "main"
    direct_scope: DirectSessionScope = DirectSessionScope.MAIN
    source: str = "http"
    queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.JUMP_QUEUE
    priority: int = Field(default=100, ge=0)
    max_steps: int | None = Field(default=None, ge=1)


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


class PromptPreviewMessageResponse(BaseModel):
    role: str
    content: Any
    name: str | None = None
    tool_call_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PromptPreviewToolSchemaResponse(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class PromptPreviewContextFileResponse(BaseModel):
    path: str
    chars: int


class PromptPreviewResponse(BaseModel):
    run_id: str
    llm_id: str
    mode: str
    messages: list[PromptPreviewMessageResponse] = Field(default_factory=list)
    tool_schemas: list[PromptPreviewToolSchemaResponse] = Field(default_factory=list)
    prompt_report: dict[str, Any] | None = None
    workspace_context_workspace: str | None = None
    workspace_context_files: list[PromptPreviewContextFileResponse] = Field(default_factory=list)

    @classmethod
    def from_dto(cls, dto: PromptPreviewDTO) -> "PromptPreviewResponse":
        return cls(
            run_id=dto.run_id,
            llm_id=dto.llm_id,
            mode=dto.mode,
            messages=[
                PromptPreviewMessageResponse(
                    role=item.role,
                    content=item.content,
                    name=item.name,
                    tool_call_id=item.tool_call_id,
                    metadata=dict(item.metadata),
                )
                for item in dto.messages
            ],
            tool_schemas=[
                PromptPreviewToolSchemaResponse(
                    name=item.name,
                    description=item.description,
                    input_schema=dict(item.input_schema),
                )
                for item in dto.tool_schemas
            ],
            prompt_report=(
                dict(dto.prompt_report)
                if dto.prompt_report is not None
                else None
            ),
            workspace_context_workspace=dto.workspace_context_workspace,
            workspace_context_files=[
                PromptPreviewContextFileResponse(
                    path=item.path,
                    chars=item.chars,
                )
                for item in dto.workspace_context_files
            ],
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
    return container.orchestration_inspection_service


def _approval_control_port(
    container: AppContainer,
) -> OrchestrationApprovalControlPort:
    return container.orchestration_approval_control_service


def _cancellation_port(container: AppContainer) -> OrchestrationCancellationPort:
    return container.orchestration_cancellation_service


def _run_lookup_port(container: AppContainer) -> OrchestrationRunLookupPort:
    return container.orchestration_run_query_service


def _scheduler_port(container: AppContainer) -> OrchestrationSchedulerRuntimePort:
    return container.orchestration_scheduler_service


def _executor_process_port(container: AppContainer) -> OrchestrationExecutorProcessPort:
    return container.orchestration_executor_service


@router.post(
    "/turns",
    response_model=TurnResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_turn(
    payload: CreateTurnRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> TurnResponse:
    profile, error = resolve_profile(
        container.agent_service,
        agent_id=payload.agent_id,
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
        main_key=payload.main_key,
        direct_scope=payload.direct_scope,
        source=payload.source,
        queue_policy=payload.queue_policy,
        priority=payload.priority,
        max_steps=payload.max_steps,
    )

    try:
        scheduler_service = _scheduler_port(container)
        run = submit_turn(
            scheduler_service,
            content=payload.content,
            options=options,
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


@router.get("/turns/{run_id}/prompt-preview", response_model=PromptPreviewResponse)
def get_turn_prompt_preview(
    run_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> PromptPreviewResponse:
    inspection_service = _inspection_port(container)
    try:
        preview = inspection_service.preview_prompt(run_id)
    except OrchestrationRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except OrchestrationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return PromptPreviewResponse.from_dto(
        PromptPreviewDTO.from_value(
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
    scheduler_service = _scheduler_port(container)
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
    scheduler_service = _scheduler_port(container)
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
    scheduler_service = _scheduler_port(container)
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
