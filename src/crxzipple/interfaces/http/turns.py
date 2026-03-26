from __future__ import annotations

import json
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from crxzipple.bootstrap import AppContainer
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.turns import (
    build_submission_options,
    extract_output_text,
    resolve_profile,
    submit_turn,
)
from crxzipple.modules.orchestration.domain import (
    ApprovalDecision,
    ApprovalResolution,
    OrchestrationRunNotFoundError,
    OrchestrationQueuePolicy,
    OrchestrationValidationError,
    PendingApprovalRequest,
)
from crxzipple.modules.orchestration.application import ResolveApprovalRequestInput
from crxzipple.modules.orchestration.application import RequestCompactionInput
from crxzipple.modules.orchestration.application import RequestHeartbeatInput
from crxzipple.modules.orchestration.application import RequestMemoryFlushInput
from crxzipple.modules.orchestration.interfaces.dto import (
    OrchestrationRunDTO,
    PromptPreviewDTO,
)
from crxzipple.modules.orchestration.interfaces.http_models import OrchestrationRunResponse
from crxzipple.modules.session.application import ListSessionMessagesInput
from crxzipple.modules.session.domain import DirectSessionScope, SessionNotFoundError
from crxzipple.modules.session.interfaces.dto import SessionMessageDTO
from crxzipple.modules.session.interfaces.http_models import SessionMessageResponse


router = APIRouter()


class CreateTurnRequest(BaseModel):
    content: str
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


class TurnSnapshotResponse(TurnResponse):
    messages: list[SessionMessageResponse] = Field(default_factory=list)


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


class TurnMessageEventResponse(BaseModel):
    run_id: str
    message: SessionMessageResponse


class TurnTextDeltaEventResponse(BaseModel):
    run_id: str
    invocation_id: str
    text_delta: str
    text: str


class TurnToolEventResponse(BaseModel):
    run_id: str
    status: str
    stage: str
    message_id: str
    tool_name: str
    tool_call_id: str | None = None
    tool_run_id: str | None = None
    tool_status: str | None = None
    created_at: str


class PendingApprovalRequestResponse(BaseModel):
    request_id: str
    effect_id: str
    label: str
    reason: str
    tool_ids: list[str]
    tool_name: str | None = None
    scope_hint: str | None = None
    created_at: str

    @classmethod
    def from_entity(
        cls,
        request: PendingApprovalRequest,
    ) -> "PendingApprovalRequestResponse":
        return cls(
            request_id=request.request_id,
            effect_id=request.effect_id,
            label=request.label,
            reason=request.reason,
            tool_ids=list(request.tool_ids),
            tool_name=request.tool_name,
            scope_hint=request.scope_hint.value if request.scope_hint is not None else None,
            created_at=request.created_at.isoformat(),
        )


class TurnApprovalRequestedEventResponse(BaseModel):
    run_id: str
    status: str
    stage: str
    request: PendingApprovalRequestResponse


class TurnApprovalResolvedEventResponse(BaseModel):
    run_id: str
    request_id: str
    decision: str
    resolved_at: str


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


def _session_key_from_run(run) -> str | None:  # noqa: ANN001
    value = run.metadata.get("session_key")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _list_turn_messages(
    container: AppContainer,
    *,
    session_key: str | None,
) -> list[SessionMessageResponse]:
    if session_key is None:
        return []
    try:
        items = container.session_service.list_messages(
            ListSessionMessagesInput(
                session_key=session_key,
                include_archived=False,
            ),
        )
    except SessionNotFoundError:
        return []
    return [SessionMessageResponse.from_dto(SessionMessageDTO.from_entity(item)) for item in items]


def _tool_started_event(
    *,
    run_payload: dict[str, object],
    message: SessionMessageResponse,
) -> TurnToolEventResponse | None:
    payload_type = message.content_payload.get("type")
    if message.role != "assistant" or payload_type != "function_call":
        return None
    tool_name = message.metadata.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name.strip():
        payload_name = message.content_payload.get("name")
        if isinstance(payload_name, str) and payload_name.strip():
            tool_name = payload_name.strip()
        else:
            return None
    tool_call_id = message.metadata.get("tool_call_id")
    if not isinstance(tool_call_id, str) or not tool_call_id.strip():
        payload_call_id = message.content_payload.get("call_id")
        tool_call_id = (
            payload_call_id.strip()
            if isinstance(payload_call_id, str) and payload_call_id.strip()
            else None
        )
    return TurnToolEventResponse(
        run_id=str(run_payload["id"]),
        status=str(run_payload["status"]),
        stage=str(run_payload["stage"]),
        message_id=message.id,
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        created_at=message.created_at,
    )


def _tool_completed_event(
    *,
    run_payload: dict[str, object],
    message: SessionMessageResponse,
) -> TurnToolEventResponse | None:
    if message.role != "tool" and "tool" not in message.kind:
        return None
    tool_name = message.metadata.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name.strip():
        payload_name = message.content_payload.get("tool_name")
        if isinstance(payload_name, str) and payload_name.strip():
            tool_name = payload_name.strip()
        else:
            return None
    tool_call_id = message.metadata.get("tool_call_id")
    if not isinstance(tool_call_id, str) or not tool_call_id.strip():
        payload_call_id = message.content_payload.get("tool_call_id")
        tool_call_id = (
            payload_call_id.strip()
            if isinstance(payload_call_id, str) and payload_call_id.strip()
            else None
        )
    payload_tool_run_id = message.content_payload.get("tool_run_id")
    tool_run_id = (
        payload_tool_run_id.strip()
        if isinstance(payload_tool_run_id, str) and payload_tool_run_id.strip()
        else None
    )
    payload_status = message.content_payload.get("status")
    tool_status = (
        payload_status.strip()
        if isinstance(payload_status, str) and payload_status.strip()
        else None
    )
    return TurnToolEventResponse(
        run_id=str(run_payload["id"]),
        status=str(run_payload["status"]),
        stage=str(run_payload["stage"]),
        message_id=message.id,
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        tool_run_id=tool_run_id,
        tool_status=tool_status,
        created_at=message.created_at,
    )


def _format_sse_event(event_name: str, payload: dict[str, object]) -> str:
    return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _pending_approval_request_from_run(run) -> PendingApprovalRequest | None:  # noqa: ANN001
    raw_request = run.metadata.get("pending_approval_request")
    if not isinstance(raw_request, dict):
        return None
    return PendingApprovalRequest.from_payload(raw_request)


def _last_approval_resolution_from_run(run) -> ApprovalResolution | None:  # noqa: ANN001
    raw_resolution = run.metadata.get("last_approval_resolution")
    if not isinstance(raw_resolution, dict):
        return None
    return ApprovalResolution.from_payload(raw_resolution)


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
        run = submit_turn(
            container.orchestration_service,
            content=payload.content,
            options=options,
        )
    except OrchestrationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    return _turn_response_from_run(run)


@router.get("/turns/{run_id}", response_model=TurnResponse)
def get_turn(
    run_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> TurnResponse:
    try:
        run = container.orchestration_service.get_run(run_id)
    except OrchestrationRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return _turn_response_from_run(run)


@router.get("/turns/{run_id}/prompt-preview", response_model=PromptPreviewResponse)
def get_turn_prompt_preview(
    run_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> PromptPreviewResponse:
    try:
        preview = container.orchestration_service.preview_prompt(run_id)
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
    try:
        run = container.orchestration_service.cancel_run(run_id, reason=payload.reason)
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
    try:
        run = container.orchestration_service.request_compaction(
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
    try:
        run = container.orchestration_service.request_heartbeat(
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
    try:
        run = container.orchestration_service.request_memory_flush(
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
    try:
        run = container.orchestration_service.resolve_approval_request(
            ResolveApprovalRequestInput(
                run_id=run_id,
                request_id=request_id,
                decision=payload.decision,
            ),
        )
        if run.status.value == "queued":
            processed = container.orchestration_service.process_next_queued_run(
                worker_id=f"http-approval:{run.id}",
            )
            if processed is not None and processed.id == run.id:
                run = processed
    except OrchestrationRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except OrchestrationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _turn_response_from_run(run)


@router.get("/turns/{run_id}/events")
def stream_turn_events(
    run_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    poll_interval_seconds: Annotated[float, Query(ge=0.05)] = 0.5,
    timeout_seconds: Annotated[float, Query(ge=1.0)] = 30.0,
) -> StreamingResponse:
    try:
        initial_run = container.orchestration_service.get_run(run_id)
    except OrchestrationRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None

    def event_stream():
        deadline = time.monotonic() + timeout_seconds
        last_signature: tuple[object, ...] | None = None
        last_message_ids: set[str] = set()
        last_stream_invocation_id: str | None = None
        last_stream_text = ""
        last_pending_approval_request_id: str | None = None
        last_approval_resolution_key: tuple[str, str, str] | None = None
        emitted_initial = False

        while time.monotonic() < deadline:
            run = container.orchestration_service.get_run(run_id)
            response = _turn_response_from_run(run)
            payload = response.model_dump(mode="json")
            run_payload = payload["run"]
            messages = _list_turn_messages(
                container,
                session_key=_session_key_from_run(run),
            )
            pending_approval_request = _pending_approval_request_from_run(run)
            approval_resolution = _last_approval_resolution_from_run(run)
            stream_invocation_id = run.metadata.get("llm_stream_invocation_id")
            stream_text = run.metadata.get("llm_stream_text")
            if not isinstance(stream_invocation_id, str) or not stream_invocation_id.strip():
                stream_invocation_id = None
            else:
                stream_invocation_id = stream_invocation_id.strip()
            if not isinstance(stream_text, str):
                stream_text = ""
            signature = (
                run_payload["status"],
                run_payload["stage"],
                run_payload["current_step"],
                tuple(run_payload["pending_tool_run_ids"]),
                run_payload["waiting_reason"],
                json.dumps(run_payload["result_payload"], sort_keys=True, ensure_ascii=False)
                if run_payload["result_payload"] is not None
                else None,
                json.dumps(run_payload["error"], sort_keys=True, ensure_ascii=False)
                if run_payload["error"] is not None
                else None,
                pending_approval_request.to_payload() if pending_approval_request is not None else None,
                approval_resolution.to_payload() if approval_resolution is not None else None,
            )

            if not emitted_initial:
                emitted_initial = True
                last_signature = signature
                last_message_ids = {item.id for item in messages}
                snapshot = TurnSnapshotResponse(
                    run=response.run,
                    output_text=response.output_text,
                    messages=messages,
                )
                yield _format_sse_event("snapshot", snapshot.model_dump(mode="json"))
                if pending_approval_request is not None:
                    approval_event = TurnApprovalRequestedEventResponse(
                        run_id=run_id,
                        status=str(run_payload["status"]),
                        stage=str(run_payload["stage"]),
                        request=PendingApprovalRequestResponse.from_entity(
                            pending_approval_request,
                        ),
                    )
                    yield _format_sse_event(
                        "approval_requested",
                        approval_event.model_dump(mode="json"),
                    )
                    last_pending_approval_request_id = pending_approval_request.request_id
            elif signature != last_signature:
                last_signature = signature
                yield _format_sse_event("updated", payload)

            if pending_approval_request is not None:
                if pending_approval_request.request_id != last_pending_approval_request_id:
                    approval_event = TurnApprovalRequestedEventResponse(
                        run_id=run_id,
                        status=str(run_payload["status"]),
                        stage=str(run_payload["stage"]),
                        request=PendingApprovalRequestResponse.from_entity(
                            pending_approval_request,
                        ),
                    )
                    yield _format_sse_event(
                        "approval_requested",
                        approval_event.model_dump(mode="json"),
                    )
                    last_pending_approval_request_id = pending_approval_request.request_id
            else:
                last_pending_approval_request_id = None

            if approval_resolution is not None:
                resolution_key = (
                    approval_resolution.request_id,
                    approval_resolution.decision.value,
                    approval_resolution.resolved_at.isoformat(),
                )
                if resolution_key != last_approval_resolution_key:
                    resolution_event = TurnApprovalResolvedEventResponse(
                        run_id=run_id,
                        request_id=approval_resolution.request_id,
                        decision=approval_resolution.decision.value,
                        resolved_at=approval_resolution.resolved_at.isoformat(),
                    )
                    yield _format_sse_event(
                        "approval_resolved",
                        resolution_event.model_dump(mode="json"),
                    )
                    last_approval_resolution_key = resolution_key

            if stream_invocation_id is not None:
                if stream_invocation_id != last_stream_invocation_id:
                    last_stream_invocation_id = stream_invocation_id
                    last_stream_text = ""
                if stream_text != last_stream_text:
                    text_delta = (
                        stream_text[len(last_stream_text) :]
                        if stream_text.startswith(last_stream_text)
                        else stream_text
                    )
                    if text_delta:
                        stream_event = TurnTextDeltaEventResponse(
                            run_id=run_id,
                            invocation_id=stream_invocation_id,
                            text_delta=text_delta,
                            text=stream_text,
                        )
                        yield _format_sse_event(
                            "llm_text_delta",
                            stream_event.model_dump(mode="json"),
                        )
                    last_stream_text = stream_text

            for message in messages:
                if message.id in last_message_ids:
                    continue
                last_message_ids.add(message.id)
                message_event = TurnMessageEventResponse(
                    run_id=run_id,
                    message=message,
                )
                yield _format_sse_event(
                    "message_appended",
                    message_event.model_dump(mode="json"),
                )
                started_event = _tool_started_event(
                    run_payload=run_payload,
                    message=message,
                )
                if started_event is not None:
                    yield _format_sse_event(
                        "tool_started",
                        started_event.model_dump(mode="json"),
                    )
                completed_event = _tool_completed_event(
                    run_payload=run_payload,
                    message=message,
                )
                if completed_event is not None:
                    yield _format_sse_event(
                        "tool_completed",
                        completed_event.model_dump(mode="json"),
                    )

            if run_payload["status"] == "completed":
                yield _format_sse_event("completed", payload)
                return
            if run_payload["status"] == "failed":
                yield _format_sse_event("failed", payload)
                return
            if run_payload["status"] == "cancelled":
                yield _format_sse_event("cancelled", payload)
                return

            time.sleep(poll_interval_seconds)

        timeout_payload = _turn_response_from_run(
            container.orchestration_service.get_run(run_id),
        ).model_dump(mode="json")
        yield _format_sse_event("timeout", timeout_payload)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
