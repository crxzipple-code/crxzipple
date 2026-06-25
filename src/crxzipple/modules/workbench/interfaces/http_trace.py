from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.http.ui_models import (
    TraceEventResponse,
    TraceSummaryResponse,
)
from crxzipple.interfaces.runtime_container import AppContainer
from crxzipple.modules.workbench.interfaces.http_dependencies import trace_provider


router = APIRouter()


@router.get("/trace/{trace_id}", response_model=TraceSummaryResponse)
def get_trace_summary(
    trace_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    focus_id: str | None = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> TraceSummaryResponse:
    view = trace_provider(container).get_trace_summary(
        trace_id,
        focus_id=focus_id,
        limit=limit,
    )
    return TraceSummaryResponse.from_view(view)


@router.get("/trace/{trace_id}/events", response_model=list[TraceEventResponse])
def list_trace_events(
    trace_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    focus_id: str | None = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[TraceEventResponse]:
    views = trace_provider(container).list_trace_events(
        trace_id,
        focus_id=focus_id,
        limit=limit,
    )
    return [TraceEventResponse.from_view(view) for view in views]
