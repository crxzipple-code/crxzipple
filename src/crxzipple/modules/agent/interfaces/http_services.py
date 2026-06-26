from __future__ import annotations

from typing import NoReturn

from fastapi import HTTPException

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.modules.agent.application import (
    AgentApplicationService,
    AgentProfileResolutionQueryService,
)
from crxzipple.modules.agent.domain.exceptions import (
    AgentAlreadyExistsError,
    AgentError,
    AgentNotFoundError,
    AgentValidationError,
)


def agent_service(container: AppContainer) -> AgentApplicationService:
    return container.require(AppKey.AGENT_SERVICE)


def agent_resolution_service(
    container: AppContainer,
) -> AgentProfileResolutionQueryService:
    return AgentProfileResolutionQueryService(
        agent_profiles=agent_service(container),
        llm_profiles=container.require(AppKey.LLM_SERVICE),
        tool_catalog=container.require(AppKey.TOOL_QUERY_SERVICE),
        access_readiness=container.require(AppKey.ACCESS_SERVICE),
        authorization_policies=container.require(AppKey.AUTHORIZATION_SERVICE),
    )


def raise_agent_http_error(exc: AgentError) -> NoReturn:
    if isinstance(exc, AgentAlreadyExistsError):
        raise HTTPException(status_code=409, detail=str(exc)) from None
    if isinstance(exc, AgentNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from None
    if isinstance(exc, AgentValidationError):
        raise HTTPException(status_code=400, detail=str(exc)) from None
    raise HTTPException(status_code=500, detail=str(exc)) from None


__all__ = [
    "agent_resolution_service",
    "agent_service",
    "raise_agent_http_error",
]
