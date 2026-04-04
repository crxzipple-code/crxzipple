from __future__ import annotations

import os
from pathlib import Path
import shutil
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from crxzipple.bootstrap import AppContainer
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.process import (
    ProcessNotFoundError,
    ProcessOutputWindow,
    ProcessSession,
    ProcessValidationError,
)


router = APIRouter()

MAX_PROCESS_COMMAND_CHARS = 8_000


class StartProcessRequest(BaseModel):
    command: str = Field(min_length=1)
    working_directory: str = Field(min_length=1)
    session_key: str | None = None


class ProcessSessionResponse(BaseModel):
    id: str
    command: str
    shell: str
    working_directory: str
    session_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    pid: int | None = None
    status: str
    exit_code: int | None = None
    created_at: str
    started_at: str
    updated_at: str
    ended_at: str | None = None
    termination_requested_at: str | None = None

    @classmethod
    def from_entity(cls, session: ProcessSession) -> "ProcessSessionResponse":
        return cls(
            id=session.id,
            command=session.command,
            shell=session.shell,
            working_directory=session.working_directory,
            session_key=session.session_key,
            metadata=dict(session.metadata),
            pid=session.pid,
            status=session.status.value,
            exit_code=session.exit_code,
            created_at=session.created_at.isoformat(),
            started_at=session.started_at.isoformat(),
            updated_at=session.updated_at.isoformat(),
            ended_at=(
                session.ended_at.isoformat() if session.ended_at is not None else None
            ),
            termination_requested_at=(
                session.termination_requested_at.isoformat()
                if session.termination_requested_at is not None
                else None
            ),
        )


class ProcessOutputResponse(BaseModel):
    process_id: str
    status: str
    exit_code: int | None = None
    stdout: str
    stderr: str
    stdout_offset: int
    stderr_offset: int
    next_stdout_offset: int
    next_stderr_offset: int
    started_at: str
    ended_at: str | None = None

    @classmethod
    def from_value_object(cls, output: ProcessOutputWindow) -> "ProcessOutputResponse":
        return cls(
            process_id=output.process_id,
            status=output.status.value,
            exit_code=output.exit_code,
            stdout=output.stdout,
            stderr=output.stderr,
            stdout_offset=output.stdout_offset,
            stderr_offset=output.stderr_offset,
            next_stdout_offset=output.next_stdout_offset,
            next_stderr_offset=output.next_stderr_offset,
            started_at=output.started_at.isoformat(),
            ended_at=output.ended_at.isoformat() if output.ended_at is not None else None,
        )


def _resolve_shell_executable() -> str:
    preferred = os.environ.get("SHELL", "").strip()
    if preferred:
        preferred_name = Path(preferred).name.lower()
        if preferred_name in {"sh", "bash", "zsh"}:
            resolved = shutil.which(preferred)
            if resolved:
                return resolved
    fallback = shutil.which("/bin/sh") or shutil.which("sh")
    if fallback:
        return fallback
    raise HTTPException(
        status_code=400,
        detail="No POSIX shell is available for process start.",
    )


def _resolve_working_directory(working_directory: str) -> str:
    try:
        resolved = Path(working_directory).expanduser().resolve(strict=True)
    except OSError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Working directory '{working_directory}' could not be resolved.",
        ) from exc
    if not resolved.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"Working directory '{working_directory}' is not a readable directory.",
        )
    return str(resolved)


def _normalize_command(command: str) -> str:
    normalized = command.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="command must be a non-empty string.")
    if len(normalized) > MAX_PROCESS_COMMAND_CHARS:
        raise HTTPException(
            status_code=400,
            detail=(
                "command is too long; maximum length is "
                f"{MAX_PROCESS_COMMAND_CHARS} characters."
            ),
        )
    return normalized


def _matches_filters(
    session: ProcessSession,
    *,
    session_key: str | None,
    working_directory: str | None,
) -> bool:
    if session_key is not None and session.session_key != session_key:
        return False
    if working_directory is not None and session.working_directory != working_directory:
        return False
    return True


def _get_process_or_404(
    container: AppContainer,
    process_id: str,
) -> ProcessSession:
    try:
        return container.process_service.get_session(process_id=process_id)
    except ProcessNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post(
    "/processes",
    response_model=ProcessSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_process(
    payload: StartProcessRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ProcessSessionResponse:
    session = container.process_service.start_command(
        command=_normalize_command(payload.command),
        shell=_resolve_shell_executable(),
        working_directory=_resolve_working_directory(payload.working_directory),
        session_key=(payload.session_key.strip() or None)
        if payload.session_key is not None
        else None,
    )
    return ProcessSessionResponse.from_entity(session)


@router.get("/processes", response_model=list[ProcessSessionResponse])
def list_processes(
    container: Annotated[AppContainer, Depends(get_container)],
    session_key: Annotated[str | None, Query(min_length=1)] = None,
    working_directory: Annotated[str | None, Query(min_length=1)] = None,
) -> list[ProcessSessionResponse]:
    normalized_working_directory = (
        _resolve_working_directory(working_directory)
        if working_directory is not None
        else None
    )
    sessions = [
        session
        for session in container.process_service.list_sessions()
        if _matches_filters(
            session,
            session_key=session_key,
            working_directory=normalized_working_directory,
        )
    ]
    return [ProcessSessionResponse.from_entity(session) for session in sessions]


@router.get("/processes/{process_id}", response_model=ProcessSessionResponse)
def get_process(
    process_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ProcessSessionResponse:
    return ProcessSessionResponse.from_entity(_get_process_or_404(container, process_id))


@router.get("/processes/{process_id}/output", response_model=ProcessOutputResponse)
def get_process_output(
    process_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    stdout_offset: Annotated[int, Query(ge=0)] = 0,
    stderr_offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=20000)] = 4000,
) -> ProcessOutputResponse:
    _get_process_or_404(container, process_id)
    output = container.process_service.read_output(
        process_id=process_id,
        stdout_offset=stdout_offset,
        stderr_offset=stderr_offset,
        limit=limit,
    )
    return ProcessOutputResponse.from_value_object(output)


@router.post("/processes/{process_id}/terminate", response_model=ProcessSessionResponse)
def terminate_process(
    process_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ProcessSessionResponse:
    _get_process_or_404(container, process_id)
    session = container.process_service.terminate_session(process_id=process_id)
    return ProcessSessionResponse.from_entity(session)


@router.delete("/processes/{process_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_process(
    process_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> None:
    _get_process_or_404(container, process_id)
    try:
        container.process_service.remove_session(process_id=process_id)
    except ProcessValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
