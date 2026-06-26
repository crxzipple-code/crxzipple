from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.agent.domain.exceptions import (
    AgentError,
)
from crxzipple.modules.agent.interfaces.dto import AgentProfileDTO
from crxzipple.modules.agent.interfaces.http_home_routes import router as home_router
from crxzipple.modules.agent.interfaces.http_models import (
    AgentProfileResolutionResponse,
    AgentProfileResponse,
    agent_profile_resolution_response as _to_resolution_response,
    agent_profile_response as _to_response,
    agent_profile_responses as _to_profile_responses,
)
from crxzipple.modules.agent.interfaces.http_requests import (
    AgentProfileActionRequest,
    RegisterAgentProfileRequest,
    UpdateAgentProfileRequest,
    agent_profile_action_input,
    profile_settings_to_input,
    register_agent_profile_input,
    update_agent_profile_input,
)
from crxzipple.modules.agent.interfaces.http_services import (
    agent_resolution_service,
    agent_service,
    raise_agent_http_error,
)


router = APIRouter()
router.include_router(home_router)


@router.post("", response_model=AgentProfileResponse, status_code=status.HTTP_201_CREATED)
def register_profile(
    payload: RegisterAgentProfileRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AgentProfileResponse:
    try:
        profile = agent_service(container).register_profile(
            register_agent_profile_input(payload),
        )
    except AgentError as exc:
        raise_agent_http_error(exc)
    return _to_response(AgentProfileDTO.from_entity(profile))


@router.get("", response_model=list[AgentProfileResponse])
def list_profiles(
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[AgentProfileResponse]:
    return _to_profile_responses(agent_service(container).list_profiles())


@router.post("/sync-profiles", response_model=list[AgentProfileResponse])
def sync_profiles(
    container: Annotated[AppContainer, Depends(get_container)],
    profile: Annotated[list[str] | None, Query()] = None,
) -> list[AgentProfileResponse]:
    selected_ids = set(profile or [])
    configured_profiles = tuple(
        item
        for item in container.require(AppKey.CORE_SETTINGS).agent_profiles
        if not selected_ids or item.id in selected_ids
    )
    synced = agent_service(container).sync_profiles(
        tuple(profile_settings_to_input(item) for item in configured_profiles),
    )
    return _to_profile_responses(synced)


@router.put("/{agent_id}", response_model=AgentProfileResponse)
def update_profile(
    agent_id: str,
    payload: UpdateAgentProfileRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AgentProfileResponse:
    try:
        profile = agent_service(container).update_profile(
            update_agent_profile_input(agent_id, payload),
        )
    except AgentError as exc:
        raise_agent_http_error(exc)
    return _to_response(AgentProfileDTO.from_entity(profile))


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(
    agent_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    reason: Annotated[str | None, Query()] = None,
    actor: Annotated[str | None, Query()] = None,
) -> Response:
    try:
        agent_service(container).delete_profile(
            agent_profile_action_input(
                agent_id,
                AgentProfileActionRequest(reason=reason, actor=actor),
            ),
        )
    except AgentError as exc:
        raise_agent_http_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{agent_id}/resolution", response_model=AgentProfileResolutionResponse)
def get_profile_resolution(
    agent_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AgentProfileResolutionResponse:
    try:
        return _to_resolution_response(
            agent_resolution_service(container).resolve(agent_id),
        )
    except AgentError as exc:
        raise_agent_http_error(exc)


@router.get("/{agent_id}", response_model=AgentProfileResponse)
def get_profile(
    agent_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AgentProfileResponse:
    try:
        profile = agent_service(container).get_profile(agent_id)
    except AgentError as exc:
        raise_agent_http_error(exc)
    return _to_response(AgentProfileDTO.from_entity(profile))


@router.post("/{agent_id}/enable", response_model=AgentProfileResponse)
def enable_profile(
    agent_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    payload: AgentProfileActionRequest | None = None,
) -> AgentProfileResponse:
    try:
        profile = agent_service(container).enable_profile(
            agent_profile_action_input(agent_id, payload),
        )
    except AgentError as exc:
        raise_agent_http_error(exc)
    return _to_response(AgentProfileDTO.from_entity(profile))


@router.post("/{agent_id}/disable", response_model=AgentProfileResponse)
def disable_profile(
    agent_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    payload: AgentProfileActionRequest | None = None,
) -> AgentProfileResponse:
    try:
        profile = agent_service(container).disable_profile(
            agent_profile_action_input(agent_id, payload),
        )
    except AgentError as exc:
        raise_agent_http_error(exc)
    return _to_response(AgentProfileDTO.from_entity(profile))
