from __future__ import annotations

from fastapi import HTTPException

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.modules.context_workspace.domain import (
    ContextNodeNotFoundError,
    ContextSnapshotNotFoundError,
    ContextWorkspaceNotFoundError,
)
from crxzipple.modules.events.application import EventTraceReadModelProvider
from crxzipple.modules.orchestration.domain import OrchestrationRunNotFoundError
from crxzipple.modules.workbench.application import (
    WorkbenchReadModelProvider,
    WorkbenchTraceReadModelProvider,
)


def workbench_provider(container: AppContainer) -> WorkbenchReadModelProvider:
    return WorkbenchReadModelProvider(
        run_query=container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE),
        tool_query=container.require(AppKey.TOOL_QUERY_SERVICE),
        artifact_query=container.require(AppKey.ARTIFACT_SERVICE),
        llm_query=container.require(AppKey.LLM_SERVICE),
        agent_query=container.require(AppKey.AGENT_SERVICE),
        session_query=container.require(AppKey.SESSION_SERVICE),
    )


def not_found(exc: OrchestrationRunNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


def context_not_found(
    exc: (
        ContextSnapshotNotFoundError
        | ContextWorkspaceNotFoundError
        | ContextNodeNotFoundError
    ),
) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


def trace_provider(container: AppContainer) -> WorkbenchTraceReadModelProvider:
    if container.require(AppKey.EVENTS_SERVICE) is None:
        raise HTTPException(status_code=503, detail="Event service is not available.")
    return WorkbenchTraceReadModelProvider(
        trace_query=EventTraceReadModelProvider(
            events_service=container.require(AppKey.EVENTS_SERVICE),
            definition_registry=container.require(AppKey.EVENT_DEFINITION_REGISTRY),
        ),
        run_query=container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE),
        context_slice_builder=container.require(AppKey.CONTEXT_SLICE_BUILDER),
    )
