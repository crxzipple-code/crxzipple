from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from crxzipple.bootstrap import AppContainer
from crxzipple.core.config import AgentProfileSettings
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.agent.application import (
    AgentHomeFileSnapshot,
    AgentHomeSnapshot,
    ExportAgentHomeInput,
    MigrateAgentHomeInput,
    RegisterAgentProfileInput,
    SyncAgentHomeInput,
    UpdateAgentHomeFilesInput,
)
from crxzipple.modules.agent.domain.exceptions import (
    AgentNotFoundError,
    AgentValidationError,
)
from crxzipple.modules.agent.domain.value_objects import (
    AgentExecutionPolicy,
    AgentIdentity,
    AgentInstructionPolicy,
    AgentLlmRoutingPolicy,
    AgentRuntimePreferences,
)
from crxzipple.modules.agent.interfaces.dto import AgentProfileDTO
from crxzipple.modules.orchestration.infrastructure import MemoryBindingService


router = APIRouter()
_memory_binding_service = MemoryBindingService()


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
    max_turns: int = 99


class AgentRuntimePreferencesRequest(BaseModel):
    home_dir: str | None = None
    workdir: str | None = None
    workspace: str | None = None
    sandbox_mode: str | None = None
    memory_retrieval_backend: str | None = None
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
    home_dir: str | None = None
    workdir: str | None = None
    workspace: str | None = None
    sandbox_mode: str | None = None
    memory_retrieval_backend: str | None = None
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


class AgentHomeMigrationResponse(BaseModel):
    source_dir: str | None = None
    home_dir: str | None = None
    workdir: str | None = None
    copied_paths: list[str] = Field(default_factory=list)
    skipped_paths: list[str] = Field(default_factory=list)
    profile: AgentProfileResponse


class AgentHomeConfigResponse(BaseModel):
    home_dir: str
    path: str
    profile: AgentProfileResponse


class AgentHomeFileResponse(BaseModel):
    name: str
    path: str
    exists: bool
    language: str
    content: str


class AgentHomeSnapshotResponse(BaseModel):
    agent_id: str
    agent_name: str
    home_dir: str
    workdir: str | None = None
    files: list[AgentHomeFileResponse]


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
        home_sidecar_files=_memory_binding_service.sidecar_files_from_runtime_preferences_payload(
            profile.runtime_preferences,
        ),
    )


@router.post("", response_model=AgentProfileResponse, status_code=status.HTTP_201_CREATED)
def register_profile(
    payload: RegisterAgentProfileRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AgentProfileResponse:
    try:
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
                    home_dir=payload.runtime_preferences.home_dir,
                    workdir=payload.runtime_preferences.workdir,
                    workspace=payload.runtime_preferences.workspace,
                    sandbox_mode=payload.runtime_preferences.sandbox_mode,
                    memory_retrieval_backend=(
                        payload.runtime_preferences.memory_retrieval_backend
                    ),
                    attrs=payload.runtime_preferences.attrs,
                ),
            ),
        )
    except AgentValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
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


@router.post("/{agent_id}/migrate-home", response_model=AgentHomeMigrationResponse)
def migrate_home(
    agent_id: str,
    payload: MigrateAgentHomeRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AgentHomeMigrationResponse:
    try:
        result = container.agent_service.migrate_profile_home(
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
        snapshot = container.agent_service.inspect_profile_home(agent_id)
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except AgentValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _to_home_snapshot_response(snapshot)


@router.put("/{agent_id}/home", response_model=AgentHomeSnapshotResponse)
def update_home(
    agent_id: str,
    payload: UpdateAgentHomeFilesRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AgentHomeSnapshotResponse:
    try:
        snapshot = container.agent_service.update_profile_home_files(
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
        result = container.agent_service.sync_profile_home(
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
        result = container.agent_service.export_profile_home(
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
            home_dir=dto.runtime_preferences.home_dir,
            workdir=dto.runtime_preferences.workdir,
            workspace=dto.runtime_preferences.workspace,
            sandbox_mode=dto.runtime_preferences.sandbox_mode,
            memory_retrieval_backend=dto.runtime_preferences.memory_retrieval_backend,
            attrs=dict(dto.runtime_preferences.attrs),
        ),
    )


def _to_home_snapshot_response(snapshot: AgentHomeSnapshot) -> AgentHomeSnapshotResponse:
    return AgentHomeSnapshotResponse(
        agent_id=snapshot.profile.id,
        agent_name=snapshot.profile.name,
        home_dir=snapshot.home_dir,
        workdir=snapshot.workdir,
        files=[_to_home_file_response(item) for item in snapshot.files],
    )


def _to_home_file_response(file: AgentHomeFileSnapshot) -> AgentHomeFileResponse:
    return AgentHomeFileResponse(
        name=file.name,
        path=file.path,
        exists=file.exists,
        language=file.language,
        content=file.content,
    )
