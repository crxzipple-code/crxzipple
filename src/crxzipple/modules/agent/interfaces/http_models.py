from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, Field

from crxzipple.modules.agent.application.home_models import (
    AgentHomeFileSnapshot,
    AgentHomeSnapshot,
    ExportAgentHomeResult,
    MigrateAgentHomeResult,
    SyncAgentHomeResult,
)
from crxzipple.modules.agent.interfaces.dto import AgentProfileDTO
from crxzipple.modules.agent.interfaces.http_resolution_models import (
    AgentProfileResolutionResponse as AgentProfileResolutionResponse,
    agent_profile_resolution_response as agent_profile_resolution_response,
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


class AgentLlmPolicyResponse(BaseModel):
    reasoning_summary_policy: str
    raw_reasoning_policy: str
    tool_use_policy: str
    parallel_tool_calls_policy: str
    final_answer_policy: str
    commentary_visibility_policy: str
    provider_external_item_policy: str


class AgentExecutionPolicyResponse(BaseModel):
    timeout_seconds: int
    max_turns: int


class AgentRuntimePreferencesResponse(BaseModel):
    home_dir: str | None = None
    workdir: str | None = None
    workspace: str | None = None
    sandbox_mode: str | None = None
    attrs: dict[str, object] = Field(default_factory=dict)


class AgentMemoryBindingResponse(BaseModel):
    enabled: bool
    scope_ref: str | None = None
    access: str


class AgentProfileResponse(BaseModel):
    id: str
    name: str
    enabled: bool
    created_at: str
    updated_at: str
    identity: AgentIdentityResponse
    instruction_policy: AgentInstructionPolicyResponse
    llm_routing_policy: AgentLlmRoutingPolicyResponse
    llm_policy: AgentLlmPolicyResponse
    execution_policy: AgentExecutionPolicyResponse
    runtime_preferences: AgentRuntimePreferencesResponse
    memory: AgentMemoryBindingResponse


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


def agent_profile_response(dto: AgentProfileDTO) -> AgentProfileResponse:
    return AgentProfileResponse(
        id=dto.id,
        name=dto.name,
        enabled=dto.enabled,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
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
        llm_policy=AgentLlmPolicyResponse(
            reasoning_summary_policy=dto.llm_policy.reasoning_summary_policy,
            raw_reasoning_policy=dto.llm_policy.raw_reasoning_policy,
            tool_use_policy=dto.llm_policy.tool_use_policy,
            parallel_tool_calls_policy=dto.llm_policy.parallel_tool_calls_policy,
            final_answer_policy=dto.llm_policy.final_answer_policy,
            commentary_visibility_policy=dto.llm_policy.commentary_visibility_policy,
            provider_external_item_policy=dto.llm_policy.provider_external_item_policy,
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
            attrs=dict(dto.runtime_preferences.attrs),
        ),
        memory=AgentMemoryBindingResponse(
            enabled=dto.memory.enabled,
            scope_ref=dto.memory.scope_ref,
            access=dto.memory.access,
        ),
    )


def agent_profile_responses(profiles: Iterable[object]) -> list[AgentProfileResponse]:
    return [
        agent_profile_response(AgentProfileDTO.from_entity(profile))
        for profile in profiles
    ]


def agent_home_snapshot_response(snapshot: AgentHomeSnapshot) -> AgentHomeSnapshotResponse:
    return AgentHomeSnapshotResponse(
        agent_id=snapshot.profile.id,
        agent_name=snapshot.profile.name,
        home_dir=snapshot.home_dir,
        workdir=snapshot.workdir,
        files=[_home_file_response(item) for item in snapshot.files],
    )


def agent_home_migration_response(
    result: MigrateAgentHomeResult,
) -> AgentHomeMigrationResponse:
    return AgentHomeMigrationResponse(
        source_dir=result.source_dir,
        home_dir=result.profile.runtime_preferences.resolved_home_dir,
        workdir=result.profile.runtime_preferences.resolved_workdir,
        copied_paths=list(result.copied_paths),
        skipped_paths=list(result.skipped_paths),
        profile=agent_profile_response(AgentProfileDTO.from_entity(result.profile)),
    )


def agent_home_config_response(
    result: SyncAgentHomeResult | ExportAgentHomeResult,
) -> AgentHomeConfigResponse:
    return AgentHomeConfigResponse(
        home_dir=result.home_dir,
        path=result.path,
        profile=agent_profile_response(AgentProfileDTO.from_entity(result.profile)),
    )


def _home_file_response(file: AgentHomeFileSnapshot) -> AgentHomeFileResponse:
    return AgentHomeFileResponse(
        name=file.name,
        path=file.path,
        exists=file.exists,
        language=file.language,
        content=file.content,
    )
