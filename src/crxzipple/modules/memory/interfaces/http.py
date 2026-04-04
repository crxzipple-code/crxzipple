from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from crxzipple.bootstrap import AppContainer
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.memory.application import (
    MemoryExcerpt,
    MemoryFileSummary,
    MemorySearchHit,
    MemoryWriteResult,
)

router = APIRouter()


def _resolve_memory_context(
    container: AppContainer,
    agent_id: str | None,
):
    context = container.memory_context_resolver.resolve(agent_id)
    if context is None:
        raise HTTPException(
            status_code=404,
            detail="No file-backed memory context is available for this agent.",
        )
    return context


class MemoryExcerptResponse(BaseModel):
    path: str
    text: str
    start_line: int
    end_line: int
    kind: str

    @classmethod
    def from_entity(cls, excerpt: MemoryExcerpt) -> "MemoryExcerptResponse":
        return cls(
            path=excerpt.path,
            text=excerpt.text,
            start_line=excerpt.start_line,
            end_line=excerpt.end_line,
            kind=excerpt.kind,
        )


class MemoryFileSummaryResponse(BaseModel):
    path: str
    kind: str
    title: str
    preview: str
    updated_at: str

    @classmethod
    def from_entity(cls, item: MemoryFileSummary) -> "MemoryFileSummaryResponse":
        return cls(
            path=item.path,
            kind=item.kind,
            title=item.title,
            preview=item.preview,
            updated_at=item.updated_at,
        )


class MemorySearchHitResponse(BaseModel):
    path: str
    snippet: str
    start_line: int
    end_line: int
    score: float
    kind: str

    @classmethod
    def from_entity(cls, item: MemorySearchHit) -> "MemorySearchHitResponse":
        return cls(
            path=item.path,
            snippet=item.snippet,
            start_line=item.start_line,
            end_line=item.end_line,
            score=item.score,
            kind=item.kind,
        )


class MemoryWriteResultResponse(BaseModel):
    path: str
    line_start: int
    line_end: int
    kind: str

    @classmethod
    def from_entity(cls, result: MemoryWriteResult) -> "MemoryWriteResultResponse":
        return cls(
            path=result.path,
            line_start=result.line_start,
            line_end=result.line_end,
            kind=result.kind,
        )


class MemoryOverviewResponse(BaseModel):
    agent_id: str
    space_id: str
    long_term: MemoryExcerptResponse | None = None
    recent_files: list[MemoryFileSummaryResponse] = Field(default_factory=list)


class WriteDailyMemoryRequest(BaseModel):
    agent_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    title: str | None = None


class WriteLongTermMemoryRequest(BaseModel):
    agent_id: str = Field(min_length=1)
    content: str = Field(min_length=1)


@router.get("/memory/overview", response_model=MemoryOverviewResponse)
def get_memory_overview(
    container: Annotated[AppContainer, Depends(get_container)],
    agent_id: str = Query(..., min_length=1),
    recent_limit: int = Query(default=12, ge=1, le=50),
) -> MemoryOverviewResponse:
    context = _resolve_memory_context(container, agent_id)
    long_term = container.file_memory_service.get(
        context=context,
        path="MEMORY.md",
    )
    if long_term is None:
        long_term = container.file_memory_service.get(
            context=context,
            path="memory.md",
        )
    recent_files = container.file_memory_service.list_files(
        context=context,
        limit=recent_limit,
    )
    return MemoryOverviewResponse(
        agent_id=agent_id,
        space_id=context.space_id,
        long_term=(
            MemoryExcerptResponse.from_entity(long_term)
            if long_term is not None
            else None
        ),
        recent_files=[
            MemoryFileSummaryResponse.from_entity(item)
            for item in recent_files
        ],
    )


@router.get("/memory/search", response_model=list[MemorySearchHitResponse])
def search_memory(
    container: Annotated[AppContainer, Depends(get_container)],
    agent_id: str = Query(..., min_length=1),
    query: str = Query(..., min_length=1),
    limit: int = Query(default=12, ge=1, le=50),
) -> list[MemorySearchHitResponse]:
    context = _resolve_memory_context(container, agent_id)
    items = container.file_memory_service.search(
        context=context,
        query=query,
        limit=limit,
    )
    return [MemorySearchHitResponse.from_entity(item) for item in items]


@router.get("/memory/excerpt", response_model=MemoryExcerptResponse)
def get_memory_excerpt(
    container: Annotated[AppContainer, Depends(get_container)],
    agent_id: str = Query(..., min_length=1),
    path: str = Query(..., min_length=1),
    start_line: int | None = Query(default=None, ge=1),
    line_count: int | None = Query(default=None, ge=1, le=500),
) -> MemoryExcerptResponse:
    context = _resolve_memory_context(container, agent_id)
    excerpt = container.file_memory_service.get(
        context=context,
        path=path,
        start_line=start_line,
        line_count=line_count,
    )
    if excerpt is None:
        raise HTTPException(status_code=404, detail="Memory excerpt was not found.")
    return MemoryExcerptResponse.from_entity(excerpt)


@router.post(
    "/memory/daily",
    response_model=MemoryWriteResultResponse,
    status_code=status.HTTP_201_CREATED,
)
def write_daily_memory(
    payload: WriteDailyMemoryRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> MemoryWriteResultResponse:
    context = _resolve_memory_context(container, payload.agent_id)
    result = container.file_memory_service.append_daily(
        context=context,
        content=payload.content,
        title=payload.title,
    )
    return MemoryWriteResultResponse.from_entity(result)


@router.post(
    "/memory/long-term",
    response_model=MemoryWriteResultResponse,
    status_code=status.HTTP_201_CREATED,
)
def write_long_term_memory(
    payload: WriteLongTermMemoryRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> MemoryWriteResultResponse:
    context = _resolve_memory_context(container, payload.agent_id)
    result = container.file_memory_service.write_long_term(
        context=context,
        content=payload.content,
    )
    return MemoryWriteResultResponse.from_entity(result)
