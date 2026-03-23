from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from crxzipple.bootstrap import AppContainer
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.session.application import (
    ListSessionInstancesInput,
    ListSessionMessagesInput,
)
from crxzipple.modules.session.domain import (
    SessionInstanceNotFoundError,
    SessionNotFoundError,
)
from crxzipple.modules.session.interfaces.dto import (
    ResolveSessionDTO,
    SessionDTO,
    SessionInstanceDTO,
    SessionMessageDTO,
)
from crxzipple.modules.session.interfaces.http_models import (
    AppendSessionMessageRequest,
    ResolveSessionRequest,
    ResolveSessionResponse,
    ResetSessionRequest,
    SessionRequest,
    SessionResponse,
    SessionInstanceResponse,
    SessionMessageResponse,
)


router = APIRouter()


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail=message)


def _not_found(
    exc: SessionNotFoundError | SessionInstanceNotFoundError,
) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def ensure_session(
    payload: SessionRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SessionResponse:
    session = container.session_service.ensure_session(
        payload.to_input(error_factory=_bad_request),
    )
    return SessionResponse.from_dto(SessionDTO.from_entity(session))


@router.get("", response_model=list[SessionResponse])
def list_sessions(
    container: Annotated[AppContainer, Depends(get_container)],
    agent_id: Annotated[str | None, Query()] = None,
) -> list[SessionResponse]:
    return [
        SessionResponse.from_dto(SessionDTO.from_entity(session))
        for session in container.session_service.list_sessions(agent_id=agent_id)
    ]


@router.post("/resolve", response_model=ResolveSessionResponse)
def resolve_session(
    payload: ResolveSessionRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ResolveSessionResponse:
    bundle = container.orchestration_service.resolve_session_bundle(payload.to_input())
    return ResolveSessionResponse.from_dto(
        ResolveSessionDTO.from_result(bundle.resolution),
    )


@router.get("/{session_key}", response_model=SessionResponse)
def get_session(
    session_key: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SessionResponse:
    try:
        session = container.session_service.get_session(session_key)
    except SessionNotFoundError as exc:
        raise _not_found(exc) from None
    return SessionResponse.from_dto(SessionDTO.from_entity(session))


@router.post(
    "/{session_key}/messages",
    response_model=SessionMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def append_message(
    session_key: str,
    payload: AppendSessionMessageRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SessionMessageResponse:
    try:
        message = container.session_service.append_message(
            payload.to_input(session_key=session_key),
        )
    except (SessionNotFoundError, SessionInstanceNotFoundError) as exc:
        raise _not_found(exc) from None
    return SessionMessageResponse.from_dto(SessionMessageDTO.from_entity(message))


@router.get("/{session_key}/messages", response_model=list[SessionMessageResponse])
def list_messages(
    session_key: str,
    container: Annotated[AppContainer, Depends(get_container)],
    limit: Annotated[int | None, Query(ge=1)] = None,
    active_session_only: Annotated[bool, Query()] = False,
) -> list[SessionMessageResponse]:
    try:
        items = container.session_service.list_messages(
            ListSessionMessagesInput(
                session_key=session_key,
                limit=limit,
                active_session_only=active_session_only,
            ),
        )
    except SessionNotFoundError as exc:
        raise _not_found(exc) from None
    return [SessionMessageResponse.from_dto(SessionMessageDTO.from_entity(item)) for item in items]


@router.get(
    "/{session_key}/instances",
    response_model=list[SessionInstanceResponse],
)
def list_instances(
    session_key: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[SessionInstanceResponse]:
    try:
        items = container.session_service.list_instances(
            ListSessionInstancesInput(session_key=session_key),
        )
    except SessionNotFoundError as exc:
        raise _not_found(exc) from None
    return [SessionInstanceResponse.from_dto(SessionInstanceDTO.from_entity(item)) for item in items]


@router.post("/{session_key}/reset", response_model=SessionResponse)
def reset_session(
    session_key: str,
    payload: ResetSessionRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SessionResponse:
    try:
        session = container.session_service.reset_session(
            payload.to_input(session_key=session_key),
        )
    except SessionNotFoundError as exc:
        raise _not_found(exc) from None
    return SessionResponse.from_dto(SessionDTO.from_entity(session))
