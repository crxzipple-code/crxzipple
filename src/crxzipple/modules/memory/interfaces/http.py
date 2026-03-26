from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from crxzipple.bootstrap import AppContainer
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.memory.application import (
    ApproveMemoryCandidateInput,
    ListMemoryCandidatesInput,
    ListMemoryEntriesInput,
    RejectMemoryCandidateInput,
)
from crxzipple.modules.memory.domain import (
    MemoryCandidate,
    MemoryCandidateNotFoundError,
    MemoryCandidateStatus,
    MemoryEntry,
)


router = APIRouter()


class MemoryCandidateResponse(BaseModel):
    id: str
    agent_id: str
    session_key: str | None = None
    run_id: str | None = None
    title: str
    content: str
    summary: str
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
    status: str
    created_at: str
    reviewed_at: str | None = None
    review_reason: str | None = None
    approved_entry_id: str | None = None

    @classmethod
    def from_entity(cls, candidate: MemoryCandidate) -> "MemoryCandidateResponse":
        return cls(
            id=candidate.id,
            agent_id=candidate.agent_id,
            session_key=candidate.session_key,
            run_id=candidate.run_id,
            title=candidate.title,
            content=candidate.content,
            summary=candidate.summary,
            tags=list(candidate.tags),
            metadata=dict(candidate.metadata),
            status=candidate.status.value,
            created_at=candidate.created_at.isoformat(),
            reviewed_at=(
                candidate.reviewed_at.isoformat()
                if candidate.reviewed_at is not None
                else None
            ),
            review_reason=candidate.review_reason,
            approved_entry_id=candidate.approved_entry_id,
        )


class MemoryEntryResponse(BaseModel):
    id: str
    agent_id: str
    session_key: str | None = None
    run_id: str | None = None
    source_candidate_id: str | None = None
    title: str
    content: str
    summary: str
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: str
    updated_at: str

    @classmethod
    def from_entity(cls, entry: MemoryEntry) -> "MemoryEntryResponse":
        return cls(
            id=entry.id,
            agent_id=entry.agent_id,
            session_key=entry.session_key,
            run_id=entry.run_id,
            source_candidate_id=entry.source_candidate_id,
            title=entry.title,
            content=entry.content,
            summary=entry.summary,
            tags=list(entry.tags),
            metadata=dict(entry.metadata),
            created_at=entry.created_at.isoformat(),
            updated_at=entry.updated_at.isoformat(),
        )


class RejectMemoryCandidateRequest(BaseModel):
    reason: str | None = None


@router.get("/memory/candidates", response_model=list[MemoryCandidateResponse])
def list_memory_candidates(
    container: Annotated[AppContainer, Depends(get_container)],
    agent_id: str | None = None,
    session_key: str | None = None,
    run_id: str | None = None,
    status_value: Annotated[str | None, Query(alias="status")] = None,
    limit: int | None = Query(default=None, ge=1, le=100),
) -> list[MemoryCandidateResponse]:
    try:
        status_filter = (
            MemoryCandidateStatus(status_value)
            if status_value is not None and status_value.strip()
            else None
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported memory candidate status '{status_value}'.",
        ) from exc
    items = container.memory_service.list_candidates(
        ListMemoryCandidatesInput(
            agent_id=agent_id,
            session_key=session_key,
            run_id=run_id,
            status=status_filter,
            limit=limit,
        ),
    )
    return [MemoryCandidateResponse.from_entity(item) for item in items]


@router.post(
    "/memory/candidates/{candidate_id}/approve",
    response_model=MemoryEntryResponse,
    status_code=status.HTTP_200_OK,
)
def approve_memory_candidate(
    candidate_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> MemoryEntryResponse:
    try:
        entry = container.memory_service.approve_candidate(
            ApproveMemoryCandidateInput(candidate_id=candidate_id),
        )
    except MemoryCandidateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return MemoryEntryResponse.from_entity(entry)


@router.post(
    "/memory/candidates/{candidate_id}/reject",
    response_model=MemoryCandidateResponse,
    status_code=status.HTTP_200_OK,
)
def reject_memory_candidate(
    candidate_id: str,
    payload: RejectMemoryCandidateRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> MemoryCandidateResponse:
    try:
        candidate = container.memory_service.reject_candidate(
            RejectMemoryCandidateInput(
                candidate_id=candidate_id,
                reason=payload.reason or "rejected",
            ),
        )
    except MemoryCandidateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return MemoryCandidateResponse.from_entity(candidate)


@router.get("/memory/entries", response_model=list[MemoryEntryResponse])
def list_memory_entries(
    container: Annotated[AppContainer, Depends(get_container)],
    agent_id: str | None = None,
    query: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=100),
) -> list[MemoryEntryResponse]:
    items = container.memory_service.list_entries(
        ListMemoryEntriesInput(
            agent_id=agent_id,
            query=query,
            limit=limit,
        ),
    )
    return [MemoryEntryResponse.from_entity(item) for item in items]
