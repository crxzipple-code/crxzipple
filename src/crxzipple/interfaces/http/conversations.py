from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from crxzipple.bootstrap import AppContainer
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.session.application import ListSessionMessagesInput
from crxzipple.modules.session.domain import SessionNotFoundError
from crxzipple.modules.session.interfaces.dto import SessionMessageDTO
from crxzipple.modules.session.interfaces.http_models import (
    SessionMessageResponse,
    SessionRuntimeBindingPayload,
)


router = APIRouter()


@dataclass(frozen=True, slots=True)
class ConversationSummaryDTO:
    bulk_key: str
    session_key: str
    active_session_id: str
    runtime_binding: SessionRuntimeBindingPayload
    status: str
    channel: str | None
    chat_type: str | None
    latest_run_id: str | None
    latest_run_status: str | None
    latest_run_stage: str | None
    last_message_preview: str | None
    created_at: str
    updated_at: str


class ConversationResponse(BaseModel):
    bulk_key: str
    session_key: str
    active_session_id: str
    runtime_binding: SessionRuntimeBindingPayload
    status: str
    channel: str | None = None
    chat_type: str | None = None
    latest_run_id: str | None = None
    latest_run_status: str | None = None
    latest_run_stage: str | None = None
    last_message_preview: str | None = None
    created_at: str
    updated_at: str

    @classmethod
    def from_dto(cls, dto: ConversationSummaryDTO) -> "ConversationResponse":
        return cls(
            bulk_key=dto.bulk_key,
            session_key=dto.session_key,
            active_session_id=dto.active_session_id,
            runtime_binding=dto.runtime_binding,
            status=dto.status,
            channel=dto.channel,
            chat_type=dto.chat_type,
            latest_run_id=dto.latest_run_id,
            latest_run_status=dto.latest_run_status,
            latest_run_stage=dto.latest_run_stage,
            last_message_preview=dto.last_message_preview,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
        )


def _resolve_session_key_for_bulk(
    container: AppContainer,
    *,
    bulk_key: str,
) -> str:
    runs = container.orchestration_service.list_runs()
    for run in sorted(runs, key=lambda item: item.created_at, reverse=True):
        if run.bulk_key != bulk_key:
            continue
        session_key = str(run.metadata.get("session_key", "")).strip()
        if session_key:
            return session_key
    raise HTTPException(
        status_code=404,
        detail=f"No conversation session was found for bulk_key '{bulk_key}'.",
    )


def _latest_run_by_bulk_key(container: AppContainer) -> dict[str, object]:
    latest: dict[str, object] = {}
    for run in sorted(
        container.orchestration_service.list_runs(),
        key=lambda item: item.updated_at,
        reverse=True,
    ):
        if run.bulk_key is None or run.bulk_key in latest:
            continue
        latest[run.bulk_key] = run
    return latest


def _last_message_preview(container: AppContainer, *, session_key: str) -> str | None:
    try:
        items = container.session_service.list_messages(
            ListSessionMessagesInput(session_key=session_key, limit=1),
        )
    except SessionNotFoundError:
        return None
    if not items:
        return None
    message = items[-1]
    if message.content is not None and message.content.strip():
        return message.content
    text_payload = message.content_payload.get("text")
    if isinstance(text_payload, str) and text_payload.strip():
        return text_payload
    return None


def _build_conversation_summary(
    container: AppContainer,
    *,
    bulk_key: str,
    session_key: str,
    latest_run,  # noqa: ANN001
) -> ConversationSummaryDTO:
    session = container.session_service.get_session(session_key)
    binding = session.runtime_binding()
    return ConversationSummaryDTO(
        bulk_key=bulk_key,
        session_key=session_key,
        active_session_id=session.active_session_id,
        runtime_binding=SessionRuntimeBindingPayload(
            agent_id=binding.agent_id,
            llm_id=binding.llm_id,
        ),
        status=session.status,
        channel=session.channel,
        chat_type=session.chat_type,
        latest_run_id=latest_run.id if latest_run is not None else None,
        latest_run_status=latest_run.status.value if latest_run is not None else None,
        latest_run_stage=latest_run.stage.value if latest_run is not None else None,
        last_message_preview=_last_message_preview(container, session_key=session_key),
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
    )


def _list_conversation_summaries(
    container: AppContainer,
) -> list[ConversationSummaryDTO]:
    items: list[ConversationSummaryDTO] = []
    latest_by_bulk = _latest_run_by_bulk_key(container)
    for bulk_key, latest_run in latest_by_bulk.items():
        session_key = str(latest_run.metadata.get("session_key", "")).strip()
        if not session_key:
            continue
        try:
            items.append(
                _build_conversation_summary(
                    container,
                    bulk_key=bulk_key,
                    session_key=session_key,
                    latest_run=latest_run,
                ),
            )
        except SessionNotFoundError:
            continue
    items.sort(key=lambda item: item.updated_at, reverse=True)
    return items


@router.get("/conversations", response_model=list[ConversationResponse])
def list_conversations(
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[ConversationResponse]:
    return [ConversationResponse.from_dto(item) for item in _list_conversation_summaries(container)]


@router.get("/conversations/{bulk_key}", response_model=ConversationResponse)
def get_conversation(
    bulk_key: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ConversationResponse:
    session_key = _resolve_session_key_for_bulk(container, bulk_key=bulk_key)
    latest_run = _latest_run_by_bulk_key(container).get(bulk_key)
    try:
        dto = _build_conversation_summary(
            container,
            bulk_key=bulk_key,
            session_key=session_key,
            latest_run=latest_run,
        )
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return ConversationResponse.from_dto(dto)


@router.get(
    "/conversations/{bulk_key}/messages",
    response_model=list[SessionMessageResponse],
)
def list_conversation_messages(
    bulk_key: str,
    container: Annotated[AppContainer, Depends(get_container)],
    limit: Annotated[int | None, Query(ge=1)] = None,
    active_session_only: Annotated[bool, Query()] = False,
) -> list[SessionMessageResponse]:
    session_key = _resolve_session_key_for_bulk(container, bulk_key=bulk_key)
    try:
        items = container.session_service.list_messages(
            ListSessionMessagesInput(
                session_key=session_key,
                limit=limit,
                active_session_only=active_session_only,
            ),
        )
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return [SessionMessageResponse.from_dto(SessionMessageDTO.from_entity(item)) for item in items]
