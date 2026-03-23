from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from crxzipple.bootstrap import AppContainer
from crxzipple.core.config import AgentProfileSettings
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.agent.application import RegisterAgentProfileInput
from crxzipple.modules.agent.domain.value_objects import (
    AgentExecutionPolicy,
    AgentIdentity,
    AgentInstructionPolicy,
    AgentLlmRoutingPolicy,
    AgentRuntimePreferences,
)
from crxzipple.modules.agent.interfaces.dto import AgentProfileDTO


router = APIRouter()


class AgentIdentityRequest(BaseModel):
    display_name: str | None = None
    theme: str | None = None
    emoji: str | None = None
    avatar: str | None = None


class AgentInstructionPolicyRequest(BaseModel):
    system_prompt: str = ""
    response_style: str | None = None
    thinking_default: str | None = None
    stream_by_default: bool = False


class AgentLlmRoutingPolicyRequest(BaseModel):
    default_llm_id: str
    fallback_llm_ids: list[str] = Field(default_factory=list)
    image_llm_id: str | None = None
    document_llm_id: str | None = None


class AgentExecutionPolicyRequest(BaseModel):
    timeout_seconds: int = 120
    max_turns: int = 12


class AgentRuntimePreferencesRequest(BaseModel):
    workspace: str | None = None
    sandbox_mode: str | None = None
    attrs: dict[str, object] = Field(default_factory=dict)


class RegisterAgentProfileRequest(BaseModel):
    id: str
    name: str
    description: str = ""
    enabled: bool = True
    identity: AgentIdentityRequest = Field(default_factory=AgentIdentityRequest)
    instruction_policy: AgentInstructionPolicyRequest = Field(
        default_factory=AgentInstructionPolicyRequest,
    )
    llm_routing_policy: AgentLlmRoutingPolicyRequest
    execution_policy: AgentExecutionPolicyRequest = Field(
        default_factory=AgentExecutionPolicyRequest,
    )
    runtime_preferences: AgentRuntimePreferencesRequest = Field(
        default_factory=AgentRuntimePreferencesRequest,
    )


class AgentIdentityResponse(BaseModel):
    display_name: str | None = None
    theme: str | None = None
    emoji: str | None = None
    avatar: str | None = None


class AgentInstructionPolicyResponse(BaseModel):
    system_prompt: str
    response_style: str | None = None
    thinking_default: str | None = None
    stream_by_default: bool


class AgentLlmRoutingPolicyResponse(BaseModel):
    default_llm_id: str
    fallback_llm_ids: list[str]
    image_llm_id: str | None = None
    document_llm_id: str | None = None


class AgentExecutionPolicyResponse(BaseModel):
    timeout_seconds: int
    max_turns: int


class AgentRuntimePreferencesResponse(BaseModel):
    workspace: str | None = None
    sandbox_mode: str | None = None
    attrs: dict[str, object] = Field(default_factory=dict)


class AgentProfileResponse(BaseModel):
    id: str
    name: str
    description: str
    enabled: bool
    identity: AgentIdentityResponse
    instruction_policy: AgentInstructionPolicyResponse
    llm_routing_policy: AgentLlmRoutingPolicyResponse
    execution_policy: AgentExecutionPolicyResponse
    runtime_preferences: AgentRuntimePreferencesResponse


def _profile_settings_to_input(profile: AgentProfileSettings) -> RegisterAgentProfileInput:
    return RegisterAgentProfileInput(
        id=profile.id,
        name=profile.name,
        description=profile.description,
        enabled=profile.enabled,
        identity=AgentIdentity.from_payload(profile.identity),
        instruction_policy=AgentInstructionPolicy.from_payload(
            profile.instruction_policy,
        ),
        llm_routing_policy=AgentLlmRoutingPolicy.from_payload(
            profile.llm_routing_policy,
        ),
        execution_policy=AgentExecutionPolicy.from_payload(profile.execution_policy),
        runtime_preferences=AgentRuntimePreferences.from_payload(
            profile.runtime_preferences,
        ),
    )


@router.post("", response_model=AgentProfileResponse, status_code=status.HTTP_201_CREATED)
def register_profile(
    payload: RegisterAgentProfileRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AgentProfileResponse:
    profile = container.agent_service.register_profile(
        RegisterAgentProfileInput(
            id=payload.id,
            name=payload.name,
            description=payload.description,
            enabled=payload.enabled,
            identity=AgentIdentity(
                display_name=payload.identity.display_name,
                theme=payload.identity.theme,
                emoji=payload.identity.emoji,
                avatar=payload.identity.avatar,
            ),
            instruction_policy=AgentInstructionPolicy(
                system_prompt=payload.instruction_policy.system_prompt,
                response_style=payload.instruction_policy.response_style,
                thinking_default=payload.instruction_policy.thinking_default,
                stream_by_default=payload.instruction_policy.stream_by_default,
            ),
            llm_routing_policy=AgentLlmRoutingPolicy(
                default_llm_id=payload.llm_routing_policy.default_llm_id,
                fallback_llm_ids=tuple(payload.llm_routing_policy.fallback_llm_ids),
                image_llm_id=payload.llm_routing_policy.image_llm_id,
                document_llm_id=payload.llm_routing_policy.document_llm_id,
            ),
            execution_policy=AgentExecutionPolicy(
                timeout_seconds=payload.execution_policy.timeout_seconds,
                max_turns=payload.execution_policy.max_turns,
            ),
            runtime_preferences=AgentRuntimePreferences(
                workspace=payload.runtime_preferences.workspace,
                sandbox_mode=payload.runtime_preferences.sandbox_mode,
                attrs=payload.runtime_preferences.attrs,
            ),
        ),
    )
    return _to_response(AgentProfileDTO.from_entity(profile))


@router.get("", response_model=list[AgentProfileResponse])
def list_profiles(
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[AgentProfileResponse]:
    return [
        _to_response(AgentProfileDTO.from_entity(profile))
        for profile in container.agent_service.list_profiles()
    ]


@router.post("/sync-profiles", response_model=list[AgentProfileResponse])
def sync_profiles(
    container: Annotated[AppContainer, Depends(get_container)],
    profile: Annotated[list[str] | None, Query()] = None,
) -> list[AgentProfileResponse]:
    selected_ids = set(profile or [])
    configured_profiles = tuple(
        item
        for item in container.settings.agent_profiles
        if not selected_ids or item.id in selected_ids
    )
    synced = container.agent_service.sync_profiles(
        tuple(_profile_settings_to_input(item) for item in configured_profiles),
    )
    return [_to_response(AgentProfileDTO.from_entity(item)) for item in synced]


@router.get("/{agent_id}", response_model=AgentProfileResponse)
def get_profile(
    agent_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AgentProfileResponse:
    return _to_response(
        AgentProfileDTO.from_entity(container.agent_service.get_profile(agent_id)),
    )


@router.post("/{agent_id}/enable", response_model=AgentProfileResponse)
def enable_profile(
    agent_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AgentProfileResponse:
    return _to_response(
        AgentProfileDTO.from_entity(container.agent_service.enable_profile(agent_id)),
    )


@router.post("/{agent_id}/disable", response_model=AgentProfileResponse)
def disable_profile(
    agent_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AgentProfileResponse:
    return _to_response(
        AgentProfileDTO.from_entity(container.agent_service.disable_profile(agent_id)),
    )


def _to_response(dto: AgentProfileDTO) -> AgentProfileResponse:
    return AgentProfileResponse(
        id=dto.id,
        name=dto.name,
        description=dto.description,
        enabled=dto.enabled,
        identity=AgentIdentityResponse(
            display_name=dto.identity.display_name,
            theme=dto.identity.theme,
            emoji=dto.identity.emoji,
            avatar=dto.identity.avatar,
        ),
        instruction_policy=AgentInstructionPolicyResponse(
            system_prompt=dto.instruction_policy.system_prompt,
            response_style=dto.instruction_policy.response_style,
            thinking_default=dto.instruction_policy.thinking_default,
            stream_by_default=dto.instruction_policy.stream_by_default,
        ),
        llm_routing_policy=AgentLlmRoutingPolicyResponse(
            default_llm_id=dto.llm_routing_policy.default_llm_id,
            fallback_llm_ids=list(dto.llm_routing_policy.fallback_llm_ids),
            image_llm_id=dto.llm_routing_policy.image_llm_id,
            document_llm_id=dto.llm_routing_policy.document_llm_id,
        ),
        execution_policy=AgentExecutionPolicyResponse(
            timeout_seconds=dto.execution_policy.timeout_seconds,
            max_turns=dto.execution_policy.max_turns,
        ),
        runtime_preferences=AgentRuntimePreferencesResponse(
            workspace=dto.runtime_preferences.workspace,
            sandbox_mode=dto.runtime_preferences.sandbox_mode,
            attrs=dict(dto.runtime_preferences.attrs),
        ),
    )
