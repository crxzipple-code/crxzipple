from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.http.ui_models import (
    ConsoleSectionResponse,
    TraceEventResponse,
    TraceSummaryResponse,
    TurnStepResponse,
    UiBootstrapResponse,
    WorkbenchHomeResponse,
    WorkbenchRunResponse,
)
from crxzipple.modules.orchestration.application.read_models import (
    WorkbenchReadModelProvider,
)
from crxzipple.modules.orchestration.domain import OrchestrationRunNotFoundError
from crxzipple.modules.events.application import EventTraceReadModelProvider
from crxzipple.shared.runtime_console import ConsoleSection


router = APIRouter()


def _workbench_provider(container: AppContainer) -> WorkbenchReadModelProvider:
    return WorkbenchReadModelProvider(
        run_query=container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE),
        tool_query=container.require(AppKey.TOOL_QUERY_SERVICE),
        artifact_query=container.require(AppKey.ARTIFACT_SERVICE),
        llm_query=container.require(AppKey.LLM_SERVICE),
        agent_query=container.require(AppKey.AGENT_SERVICE),
    )


def _trace_provider(container: AppContainer) -> EventTraceReadModelProvider:
    if container.require(AppKey.EVENTS_SERVICE) is None:
        raise HTTPException(status_code=503, detail="Event service is not available.")
    return EventTraceReadModelProvider(
        events_service=container.require(AppKey.EVENTS_SERVICE),
        definition_registry=container.require(AppKey.EVENT_DEFINITION_REGISTRY),
    )


def _not_found(exc: OrchestrationRunNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


@router.get("/bootstrap", response_model=UiBootstrapResponse)
def bootstrap(
    container: Annotated[AppContainer, Depends(get_container)],
) -> UiBootstrapResponse:
    sections = [
        ConsoleSection(
            id="workbench",
            owner="orchestration",
            status="ready",
            updated_at=None,
            data={"preferred_refresh": "sse+query"},
        ),
        ConsoleSection(
            id="events",
            owner="events",
            status="ready" if container.require(AppKey.EVENTS_SERVICE) is not None else "degraded",
            updated_at=None,
            data={"stream_available": container.require(AppKey.EVENTS_SERVICE) is not None},
        ),
    ]
    return UiBootstrapResponse(
        version=1,
        app_name=container.require(AppKey.CORE_SETTINGS).app_name,
        environment=container.require(AppKey.CORE_SETTINGS).environment,
        routes=[
            "/ui/bootstrap",
            "/ui/access",
            "/ui/access/assets",
            "/ui/access/assets/{asset_id}",
            "/ui/access/policies",
            "/ui/access/consumers",
            "/authorization/policies",
            "/authorization/policies/{policy_id}",
            "/authorization/policies/{policy_id}/enable",
            "/authorization/policies/{policy_id}/disable",
            "/authorization/policies/import",
            "/authorization/policies/export",
            "/authorization/policies/dry-run",
            "/authorization/policies/impact",
            "/authorization/audits",
            "/ui/workbench/home",
            "/ui/workbench/runs/{run_id}",
            "/ui/workbench/runs/{run_id}/steps",
            "/operations/orchestration",
            "/operations/tool",
            "/operations/browser",
            "/operations/llm",
            "/operations/access",
            "/operations/channels",
            "/operations/memory",
            "/operations/skills",
            "/operations/events",
            "/operations/daemon",
            "/operations/runtime",
            "/operations/orchestration/overview",
            "/operations/tool/overview",
            "/operations/browser/overview",
            "/operations/llm/overview",
            "/operations/access/overview",
            "/operations/channels/overview",
            "/operations/memory/overview",
            "/operations/skills/overview",
            "/operations/events/overview",
            "/operations/daemon/overview",
            "/operations/{module}/overview",
            "/operations/events/subscriptions/advance-to-head",
            "/operations/events/observers/advance-to-head",
            "/operations/channels/runtimes/prune-stale",
            "/operations/channels/dead-letters/{channel_type}/replay",
            "/operations/memory/long-term",
            "/operations/llm/invocations/{invocation_id}/detail",
            "/operations/orchestration/runs/{run_id}/cancel",
            "/operations/orchestration/runs/{run_id}/resume",
            "/operations/tool/runs/{run_id}/detail",
            "/operations/tool/runs/{run_id}/cancel",
            "/operations/tool/runs/{run_id}/retry",
            "/operations/tool/workers/prune-expired",
            "/operations/access/inventory",
            "/operations/access/check",
            "/operations/access/setup",
            "/operations/daemon/services/{service_key}/ensure",
            "/operations/daemon/services/{service_key}/healthcheck",
            "/operations/daemon/services/{service_key}/reconcile",
            "/operations/daemon/services/{service_key}/stop",
            "/operations/skills/validate",
            "/operations/skills/sync",
            "/operations/skills/install",
            "/turns",
            "/turns/{run_id}",
            "/turns/{run_id}/prompt-preview",
            "/turns/{run_id}/compact",
            "/turns/{run_id}/heartbeat",
            "/turns/{run_id}/memory-flush",
            "/turns/{run_id}/approvals/{request_id}",
            "/ui/trace/{trace_id}",
            "/ui/trace/{trace_id}/events",
        ],
        sections=[ConsoleSectionResponse.from_value(item) for item in sections],
    )


@router.get("/workbench/home", response_model=WorkbenchHomeResponse)
def get_workbench_home(
    container: Annotated[AppContainer, Depends(get_container)],
    run_id: str | None = Query(default=None),
    session_key: str | None = Query(default=None),
) -> WorkbenchHomeResponse:
    view = _workbench_provider(container).get_home_view(
        run_id=run_id,
        session_key=session_key,
    )
    return WorkbenchHomeResponse.from_view(view)


@router.get("/workbench/runs/{run_id}", response_model=WorkbenchRunResponse)
def get_workbench_run(
    run_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> WorkbenchRunResponse:
    try:
        view = _workbench_provider(container).get_run_view(run_id)
    except OrchestrationRunNotFoundError as exc:
        raise _not_found(exc) from None
    return WorkbenchRunResponse.from_view(view)


@router.get("/workbench/runs/{run_id}/steps", response_model=list[TurnStepResponse])
def list_workbench_run_steps(
    run_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[TurnStepResponse]:
    try:
        views = _workbench_provider(container).list_step_views(run_id)
    except OrchestrationRunNotFoundError as exc:
        raise _not_found(exc) from None
    return [TurnStepResponse.from_view(view) for view in views]


@router.get("/trace/{trace_id}", response_model=TraceSummaryResponse)
def get_trace_summary(
    trace_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> TraceSummaryResponse:
    aliases = _trace_aliases(container, trace_id)
    view = _trace_provider(container).get_trace(
        trace_id,
        aliases=aliases,
        limit=limit,
    )
    return TraceSummaryResponse.from_view(view)


@router.get("/trace/{trace_id}/events", response_model=list[TraceEventResponse])
def list_trace_events(
    trace_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[TraceEventResponse]:
    aliases = _trace_aliases(container, trace_id)
    views = _trace_provider(container).list_trace_events(
        trace_id,
        aliases=aliases,
        limit=limit,
    )
    return [TraceEventResponse.from_view(view) for view in views]


def _trace_aliases(container: AppContainer, trace_id: str) -> set[str]:
    normalized = trace_id.strip()
    aliases = {normalized} if normalized else set()
    if not normalized:
        return aliases
    for run in container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE).list_runs():
        metadata_trace_id = run.metadata.get("trace_id")
        metadata_correlation_id = run.metadata.get("correlation_id")
        if normalized in {
            run.id,
            run.session_key,
            metadata_trace_id if isinstance(metadata_trace_id, str) else None,
            metadata_correlation_id if isinstance(metadata_correlation_id, str) else None,
        }:
            aliases.add(run.id)
            if run.session_key is not None:
                aliases.add(run.session_key)
            if isinstance(metadata_trace_id, str) and metadata_trace_id.strip():
                aliases.add(metadata_trace_id.strip())
            if isinstance(metadata_correlation_id, str) and metadata_correlation_id.strip():
                aliases.add(metadata_correlation_id.strip())
    return aliases
