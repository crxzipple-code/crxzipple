from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.runtime_container import AppContainer
from crxzipple.modules.operations.interfaces.http_models import (
    AccessOperationsResponse,
    ChannelsOperationsResponse,
    EventsOperationsResponse,
    MemoryOperationsResponse,
    SkillsOperationsResponse,
)
from crxzipple.modules.operations.interfaces.http_projection_helpers import (
    projection_response,
)

router = APIRouter()


@router.get("/memory", response_model=MemoryOperationsResponse)
def get_memory_operations(
    container: Annotated[AppContainer, Depends(get_container)],
    agent_id: str = Query(default=""),
    kind: str = Query(default="all"),
    search: str = Query(default=""),
    limit: int = Query(default=80, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> MemoryOperationsResponse:
    return projection_response(
        container,
        module="memory",
        response_cls=MemoryOperationsResponse,
        table="source_files",
        filters={
            "agent_id": agent_id,
            "kind": kind,
            "search": search,
            "limit": limit,
            "offset": offset,
        },
    )


@router.get("/skills", response_model=SkillsOperationsResponse)
def get_skills_operations(
    container: Annotated[AppContainer, Depends(get_container)],
    surface: str = Query(default="interactive"),
    source: str = Query(default="all"),
    status: str = Query(default="all"),
    search: str = Query(default=""),
    limit: int = Query(default=80, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> SkillsOperationsResponse:
    return projection_response(
        container,
        module="skills",
        response_cls=SkillsOperationsResponse,
        table="recently_resolved_skills",
        filters={
            "surface": surface,
            "source": source,
            "status": status,
            "search": search,
            "limit": limit,
            "offset": offset,
        },
    )


@router.get("/access", response_model=AccessOperationsResponse)
def get_access_operations(
    container: Annotated[AppContainer, Depends(get_container)],
    status: str = Query(default="all"),
    kind: str = Query(default="all"),
    usage_type: str = Query(default="all"),
    search: str = Query(default=""),
    include_ready: bool = Query(default=True),
    include_disabled: bool = Query(default=False),
    limit: int = Query(default=80, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AccessOperationsResponse:
    return projection_response(
        container,
        module="access",
        response_cls=AccessOperationsResponse,
        table="access_targets",
        filters={
            "status": status,
            "kind": kind,
            "usage_type": usage_type,
            "search": search,
            "include_ready": include_ready,
            "include_disabled": include_disabled,
            "limit": limit,
            "offset": offset,
        },
    )


@router.get("/channels", response_model=ChannelsOperationsResponse)
def get_channels_operations(
    container: Annotated[AppContainer, Depends(get_container)],
    status: str = Query(default="all"),
    channel_type: str = Query(default="all"),
    search: str = Query(default=""),
    limit: int = Query(default=80, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ChannelsOperationsResponse:
    return projection_response(
        container,
        module="channels",
        response_cls=ChannelsOperationsResponse,
        table="channel_status",
        filters={
            "status": status,
            "channel_type": channel_type,
            "search": search,
            "limit": limit,
            "offset": offset,
        },
    )


@router.get("/events", response_model=EventsOperationsResponse)
def get_events_operations(
    container: Annotated[AppContainer, Depends(get_container)],
    status: str = Query(default="all"),
    topic_prefix: str = Query(default=""),
    search: str = Query(default=""),
    owner: str = Query(default="all"),
    limit: int = Query(default=80, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> EventsOperationsResponse:
    return projection_response(
        container,
        module="events",
        response_cls=EventsOperationsResponse,
        table="recent_events",
        filters={
            "status": status,
            "topic_prefix": topic_prefix,
            "search": search,
            "owner": owner,
            "limit": limit,
            "offset": offset,
        },
    )
