from __future__ import annotations

import json
import time
from typing import Annotated

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
    OrchestrationRunNotFoundError,
    OrchestrationQueuePolicy,
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.interfaces.dto import OrchestrationRunDTO
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


class CancelTurnRequest(BaseModel):
    reason: str | None = None


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
            ListSessionMessagesInput(session_key=session_key),
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
            elif signature != last_signature:
                last_signature = signature
                yield _format_sse_event("updated", payload)

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
