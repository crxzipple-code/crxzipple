from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.core.config import AgentProfileSettings
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.agent.application import (
    AgentProfileActionInput,
    AgentProfileResolutionQueryService,
    ExportAgentHomeInput,
    MigrateAgentHomeInput,
    RegisterAgentProfileInput,
    SyncAgentHomeInput,
    UpdateAgentHomeFilesInput,
    UpdateAgentProfileInput,
)
from crxzipple.modules.agent.domain.exceptions import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
    AgentValidationError,
)
from crxzipple.modules.agent.domain.value_objects import (
    AgentExecutionPolicy,
    AgentIdentity,
    AgentInstructionPolicy,
    AgentLlmPolicy,
    AgentLlmRoutingPolicy,
    AgentMemoryBinding,
    AgentRuntimePreferences,
)
from crxzipple.modules.agent.interfaces.dto import AgentProfileDTO
from crxzipple.modules.agent.interfaces.http_models import (
    AgentHomeConfigResponse,
    AgentHomeMigrationResponse,
    AgentHomeSnapshotResponse,
    AgentProfileResolutionResponse,
    AgentProfileResponse,
    agent_home_snapshot_response as _to_home_snapshot_response,
    agent_profile_resolution_response as _to_resolution_response,
    agent_profile_response as _to_response,
)


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


class AgentLlmPolicyRequest(BaseModel):
    reasoning_summary_policy: str = "visible_and_replay_when_provider_supports"
    raw_reasoning_policy: str = "hidden_by_default"
    tool_use_policy: str = "auto"
    parallel_tool_calls_policy: str = "provider_default"
    final_answer_policy: str = "phase_or_codex_unknown_fallback"
    commentary_visibility_policy: str = "user_progress"
    provider_external_item_policy: str = "history_and_trace_no_toolrun"


class AgentExecutionPolicyRequest(BaseModel):
    timeout_seconds: int = 120
    max_turns: int = 99


class AgentRuntimePreferencesRequest(BaseModel):
    home_dir: str | None = None
    workdir: str | None = None
    workspace: str | None = None
    sandbox_mode: str | None = None
    attrs: dict[str, object] = Field(default_factory=dict)


class AgentMemoryBindingRequest(BaseModel):
    enabled: bool = True
    scope_ref: str | None = None
    access: str = "read_write"


class RegisterAgentProfileRequest(BaseModel):
    id: str
    name: str
    enabled: bool = True
    identity: AgentIdentityRequest = Field(default_factory=AgentIdentityRequest)
    instruction_policy: AgentInstructionPolicyRequest = Field(
        default_factory=AgentInstructionPolicyRequest,
    )
    llm_routing_policy: AgentLlmRoutingPolicyRequest
    llm_policy: AgentLlmPolicyRequest = Field(default_factory=AgentLlmPolicyRequest)
    execution_policy: AgentExecutionPolicyRequest = Field(
        default_factory=AgentExecutionPolicyRequest,
    )
    runtime_preferences: AgentRuntimePreferencesRequest = Field(
        default_factory=AgentRuntimePreferencesRequest,
    )
    memory: AgentMemoryBindingRequest = Field(default_factory=AgentMemoryBindingRequest)
    reason: str | None = None
    actor: str | None = None


class UpdateAgentProfileRequest(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    identity: AgentIdentityRequest | None = None
    instruction_policy: AgentInstructionPolicyRequest | None = None
    llm_routing_policy: AgentLlmRoutingPolicyRequest | None = None
    llm_policy: AgentLlmPolicyRequest | None = None
    execution_policy: AgentExecutionPolicyRequest | None = None
    runtime_preferences: AgentRuntimePreferencesRequest | None = None
    memory: AgentMemoryBindingRequest | None = None
    reason: str | None = None
    actor: str | None = None


class AgentProfileActionRequest(BaseModel):
    reason: str | None = None
    actor: str | None = None


class MigrateAgentHomeRequest(BaseModel):
    home_dir: str
    workdir: str | None = None


class SyncAgentHomeRequest(BaseModel):
    home_dir: str | None = None


class ExportAgentHomeRequest(BaseModel):
    home_dir: str | None = None


class AgentHomeFileRequest(BaseModel):
    name: str
    content: str


class UpdateAgentHomeFilesRequest(BaseModel):
    files: list[AgentHomeFileRequest] = Field(default_factory=list)


@router.post("", response_model=AgentProfileResponse, status_code=status.HTTP_201_CREATED)
def register_profile(
    payload: RegisterAgentProfileRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AgentProfileResponse:
    try:
        profile = container.require(AppKey.AGENT_SERVICE).register_profile(
            _register_request_to_input(payload),
        )
    except AgentAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except AgentValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _to_response(AgentProfileDTO.from_entity(profile))


@router.get("", response_model=list[AgentProfileResponse])
def list_profiles(
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[AgentProfileResponse]:
    return [
        _to_response(AgentProfileDTO.from_entity(profile))
        for profile in container.require(AppKey.AGENT_SERVICE).list_profiles()
    ]


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
    synced = container.require(AppKey.AGENT_SERVICE).sync_profiles(
        tuple(_profile_settings_to_input(item) for item in configured_profiles),
    )
    return [_to_response(AgentProfileDTO.from_entity(item)) for item in synced]


@router.put("/{agent_id}", response_model=AgentProfileResponse)
def update_profile(
    agent_id: str,
    payload: UpdateAgentProfileRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AgentProfileResponse:
    try:
        profile = container.require(AppKey.AGENT_SERVICE).update_profile(
            _update_request_to_input(agent_id, payload),
        )
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except AgentValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _to_response(AgentProfileDTO.from_entity(profile))


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(
    agent_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    reason: Annotated[str | None, Query()] = None,
    actor: Annotated[str | None, Query()] = None,
) -> Response:
    try:
        container.require(AppKey.AGENT_SERVICE).delete_profile(
            AgentProfileActionInput(id=agent_id, reason=reason, actor=actor),
        )
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except AgentValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{agent_id}/migrate-home", response_model=AgentHomeMigrationResponse)
def migrate_home(
    agent_id: str,
    payload: MigrateAgentHomeRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AgentHomeMigrationResponse:
    try:
        result = container.require(AppKey.AGENT_SERVICE).migrate_profile_home(
            MigrateAgentHomeInput(
                id=agent_id,
                home_dir=payload.home_dir,
                workdir=payload.workdir,
            ),
        )
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except AgentValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return AgentHomeMigrationResponse(
        source_dir=result.source_dir,
        home_dir=result.profile.runtime_preferences.resolved_home_dir,
        workdir=result.profile.runtime_preferences.resolved_workdir,
        copied_paths=list(result.copied_paths),
        skipped_paths=list(result.skipped_paths),
        profile=_to_response(AgentProfileDTO.from_entity(result.profile)),
    )


@router.get("/{agent_id}/home", response_model=AgentHomeSnapshotResponse)
def get_home(
    agent_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AgentHomeSnapshotResponse:
    try:
        snapshot = container.require(AppKey.AGENT_SERVICE).inspect_profile_home(agent_id)
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except AgentValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _to_home_snapshot_response(snapshot)


@router.get("/{agent_id}/resolution", response_model=AgentProfileResolutionResponse)
def get_profile_resolution(
    agent_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AgentProfileResolutionResponse:
    service = AgentProfileResolutionQueryService(
        agent_profiles=container.require(AppKey.AGENT_SERVICE),
        llm_profiles=container.require(AppKey.LLM_SERVICE),
        tool_catalog=container.require(AppKey.TOOL_QUERY_SERVICE),
        access_readiness=container.require(AppKey.ACCESS_SERVICE),
        authorization_policies=container.require(AppKey.AUTHORIZATION_SERVICE),
    )
    try:
        return _to_resolution_response(service.resolve(agent_id))
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.put("/{agent_id}/home", response_model=AgentHomeSnapshotResponse)
def update_home(
    agent_id: str,
    payload: UpdateAgentHomeFilesRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AgentHomeSnapshotResponse:
    try:
        snapshot = container.require(AppKey.AGENT_SERVICE).update_profile_home_files(
            UpdateAgentHomeFilesInput(
                id=agent_id,
                files={item.name: item.content for item in payload.files},
            ),
        )
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except AgentValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _to_home_snapshot_response(snapshot)


@router.post("/{agent_id}/sync-home", response_model=AgentHomeConfigResponse)
def sync_home(
    agent_id: str,
    payload: SyncAgentHomeRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AgentHomeConfigResponse:
    try:
        result = container.require(AppKey.AGENT_SERVICE).sync_profile_home(
            SyncAgentHomeInput(
                id=agent_id,
                home_dir=payload.home_dir,
            ),
        )
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except AgentValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return AgentHomeConfigResponse(
        home_dir=result.home_dir,
        path=result.path,
        profile=_to_response(AgentProfileDTO.from_entity(result.profile)),
    )


@router.post("/{agent_id}/export-home", response_model=AgentHomeConfigResponse)
def export_home(
    agent_id: str,
    payload: ExportAgentHomeRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AgentHomeConfigResponse:
    try:
        result = container.require(AppKey.AGENT_SERVICE).export_profile_home(
            ExportAgentHomeInput(
                id=agent_id,
                home_dir=payload.home_dir,
            ),
        )
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except AgentValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return AgentHomeConfigResponse(
        home_dir=result.home_dir,
        path=result.path,
        profile=_to_response(AgentProfileDTO.from_entity(result.profile)),
    )


@router.get("/{agent_id}", response_model=AgentProfileResponse)
def get_profile(
    agent_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AgentProfileResponse:
    try:
        profile = container.require(AppKey.AGENT_SERVICE).get_profile(agent_id)
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return _to_response(AgentProfileDTO.from_entity(profile))


@router.post("/{agent_id}/enable", response_model=AgentProfileResponse)
def enable_profile(
    agent_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    payload: AgentProfileActionRequest | None = None,
) -> AgentProfileResponse:
    try:
        profile = container.require(AppKey.AGENT_SERVICE).enable_profile(
            _action_request_to_input(agent_id, payload),
        )
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return _to_response(AgentProfileDTO.from_entity(profile))


@router.post("/{agent_id}/disable", response_model=AgentProfileResponse)
def disable_profile(
    agent_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    payload: AgentProfileActionRequest | None = None,
) -> AgentProfileResponse:
    try:
        profile = container.require(AppKey.AGENT_SERVICE).disable_profile(
            _action_request_to_input(agent_id, payload),
        )
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return _to_response(AgentProfileDTO.from_entity(profile))


def _register_request_to_input(
    payload: RegisterAgentProfileRequest,
) -> RegisterAgentProfileInput:
    return RegisterAgentProfileInput(
        id=payload.id,
        name=payload.name,
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
        llm_policy=AgentLlmPolicy.from_payload(payload.llm_policy.model_dump()),
        execution_policy=AgentExecutionPolicy(
            timeout_seconds=payload.execution_policy.timeout_seconds,
            max_turns=payload.execution_policy.max_turns,
        ),
        runtime_preferences=AgentRuntimePreferences(
            home_dir=payload.runtime_preferences.home_dir,
            workdir=payload.runtime_preferences.workdir,
            workspace=payload.runtime_preferences.workspace,
            sandbox_mode=payload.runtime_preferences.sandbox_mode,
            attrs=dict(payload.runtime_preferences.attrs),
        ),
        memory=AgentMemoryBinding(
            enabled=payload.memory.enabled,
            scope_ref=payload.memory.scope_ref,
            access=payload.memory.access,
        ),
        reason=payload.reason,
        actor=payload.actor,
    )


def _update_request_to_input(
    agent_id: str,
    payload: UpdateAgentProfileRequest,
) -> UpdateAgentProfileInput:
    updates: dict[str, object] = {}
    if payload.name is not None:
        updates["name"] = payload.name
    if payload.enabled is not None:
        updates["enabled"] = payload.enabled
    if payload.identity is not None:
        updates["identity"] = AgentIdentity(
            display_name=payload.identity.display_name,
            theme=payload.identity.theme,
            emoji=payload.identity.emoji,
            avatar=payload.identity.avatar,
        )
    if payload.instruction_policy is not None:
        updates["instruction_policy"] = AgentInstructionPolicy(
            system_prompt=payload.instruction_policy.system_prompt,
            response_style=payload.instruction_policy.response_style,
            thinking_default=payload.instruction_policy.thinking_default,
            stream_by_default=payload.instruction_policy.stream_by_default,
        )
    if payload.llm_routing_policy is not None:
        updates["llm_routing_policy"] = AgentLlmRoutingPolicy(
            default_llm_id=payload.llm_routing_policy.default_llm_id,
            fallback_llm_ids=tuple(payload.llm_routing_policy.fallback_llm_ids),
            image_llm_id=payload.llm_routing_policy.image_llm_id,
            document_llm_id=payload.llm_routing_policy.document_llm_id,
        )
    if payload.llm_policy is not None:
        updates["llm_policy"] = AgentLlmPolicy.from_payload(
            payload.llm_policy.model_dump(),
        )
    if payload.execution_policy is not None:
        updates["execution_policy"] = AgentExecutionPolicy(
            timeout_seconds=payload.execution_policy.timeout_seconds,
            max_turns=payload.execution_policy.max_turns,
        )
    if payload.runtime_preferences is not None:
        updates["runtime_preferences"] = AgentRuntimePreferences(
            home_dir=payload.runtime_preferences.home_dir,
            workdir=payload.runtime_preferences.workdir,
            workspace=payload.runtime_preferences.workspace,
            sandbox_mode=payload.runtime_preferences.sandbox_mode,
            attrs=dict(payload.runtime_preferences.attrs),
        )
    if payload.memory is not None:
        updates["memory"] = AgentMemoryBinding(
            enabled=payload.memory.enabled,
            scope_ref=payload.memory.scope_ref,
            access=payload.memory.access,
        )
    return UpdateAgentProfileInput(
        id=agent_id,
        reason=payload.reason,
        actor=payload.actor,
        **updates,
    )


def _action_request_to_input(
    agent_id: str,
    payload: AgentProfileActionRequest | None,
) -> AgentProfileActionInput:
    return AgentProfileActionInput(
        id=agent_id,
        reason=payload.reason if payload is not None else None,
        actor=payload.actor if payload is not None else None,
    )


def _profile_settings_to_input(profile: AgentProfileSettings) -> RegisterAgentProfileInput:
    return RegisterAgentProfileInput(
        id=profile.id,
        name=profile.name,
        enabled=profile.enabled,
        identity=AgentIdentity.from_payload(profile.identity),
        instruction_policy=AgentInstructionPolicy.from_payload(
            profile.instruction_policy,
        ),
        llm_routing_policy=AgentLlmRoutingPolicy.from_payload(
            profile.llm_routing_policy,
        ),
        llm_policy=AgentLlmPolicy.from_payload(profile.llm_policy),
        execution_policy=AgentExecutionPolicy.from_payload(profile.execution_policy),
        runtime_preferences=AgentRuntimePreferences.from_payload(
            profile.runtime_preferences,
        ),
        memory=AgentMemoryBinding.from_payload(profile.memory),
    )
