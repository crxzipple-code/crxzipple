from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.runtime_container import AppContainer
from crxzipple.modules.operations.interfaces.http_models import (
    BrowserOperationsResponse,
    DaemonOperationsResponse,
    LlmOperationsResponse,
    OrchestrationOperationsResponse,
    ToolOperationsResponse,
)
from crxzipple.modules.operations.interfaces.http_projection_helpers import (
    projection_response,
)

router = APIRouter()


@router.get("/orchestration", response_model=OrchestrationOperationsResponse)
def get_orchestration_operations(
    container: Annotated[AppContainer, Depends(get_container)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> OrchestrationOperationsResponse:
    return projection_response(
        container,
        module="orchestration",
        response_cls=OrchestrationOperationsResponse,
        table="run_queue",
        filters={
            "status": "all",
            "search": "",
            "limit": limit,
            "offset": offset,
        },
    )


@router.get("/tool", response_model=ToolOperationsResponse)
def get_tool_operations(
    container: Annotated[AppContainer, Depends(get_container)],
    status: str = Query(default="all"),
    time_window: str = Query(default="all"),
    search: str = Query(default=""),
    tool_id: str = Query(default="all"),
    provider: str = Query(default="all"),
    mode: str = Query(default="all"),
    strategy: str = Query(default="all"),
    environment: str = Query(default="all"),
    worker_id: str = Query(default="all"),
    has_artifact: str = Query(default="all"),
    retryable: str = Query(default="all"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ToolOperationsResponse:
    return projection_response(
        container,
        module="tool",
        response_cls=ToolOperationsResponse,
        table="tool_runs",
        filters={
            "status": status,
            "time_window": time_window,
            "search": search,
            "tool_id": tool_id,
            "provider": provider,
            "mode": mode,
            "strategy": strategy,
            "environment": environment,
            "worker_id": worker_id,
            "has_artifact": has_artifact,
            "retryable": retryable,
            "limit": limit,
            "offset": offset,
        },
    )


@router.get("/browser", response_model=BrowserOperationsResponse)
def get_browser_operations(
    container: Annotated[AppContainer, Depends(get_container)],
    status: str = Query(default="all"),
    profile: str = Query(default="all"),
    search: str = Query(default=""),
    limit: int = Query(default=80, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> BrowserOperationsResponse:
    return projection_response(
        container,
        module="browser",
        response_cls=BrowserOperationsResponse,
        table="profiles",
        filters={
            "status": status,
            "profile": profile,
            "search": search,
            "limit": limit,
            "offset": offset,
        },
    )


@router.get("/llm", response_model=LlmOperationsResponse)
def get_llm_operations(
    container: Annotated[AppContainer, Depends(get_container)],
    status: str = Query(default="all"),
    time_window: str = Query(default="all"),
    search: str = Query(default=""),
    llm_id: str = Query(default="all"),
    run_id: str = Query(default="all"),
    provider: str = Query(default="all"),
    streaming: str = Query(default="all"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> LlmOperationsResponse:
    return projection_response(
        container,
        module="llm",
        response_cls=LlmOperationsResponse,
        table="recent_invocations",
        filters={
            "status": status,
            "time_window": time_window,
            "search": search,
            "llm_id": llm_id,
            "run_id": run_id,
            "provider": provider,
            "streaming": streaming,
            "limit": limit,
            "offset": offset,
        },
    )


@router.get("/daemon", response_model=DaemonOperationsResponse)
def get_daemon_operations(
    container: Annotated[AppContainer, Depends(get_container)],
    status: str = Query(default="all"),
    service_key: str = Query(default="all"),
    service_group: str = Query(default="all"),
    search: str = Query(default=""),
    limit: int = Query(default=80, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> DaemonOperationsResponse:
    return projection_response(
        container,
        module="daemon",
        response_cls=DaemonOperationsResponse,
        table="services",
        filters={
            "status": status,
            "service_key": service_key,
            "service_group": service_group,
            "search": search,
            "limit": limit,
            "offset": offset,
        },
    )
