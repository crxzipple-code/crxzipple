from __future__ import annotations

from crxzipple.modules.agent.application.home_models import (
    ExportAgentHomeInput,
    MigrateAgentHomeInput,
    SyncAgentHomeInput,
    UpdateAgentHomeFilesInput,
)
from crxzipple.modules.agent.application.profile_models import (
    AgentProfileActionInput,
    RegisterAgentProfileInput,
    UpdateAgentProfileInput,
)
from crxzipple.modules.agent.application.settings_integration import (
    agent_profile_input_from_settings,
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
from crxzipple.modules.agent.interfaces.http_request_models import (
    AgentExecutionPolicyRequest as AgentExecutionPolicyRequest,
    AgentHomeFileRequest as AgentHomeFileRequest,
    AgentIdentityRequest as AgentIdentityRequest,
    AgentInstructionPolicyRequest as AgentInstructionPolicyRequest,
    AgentLlmPolicyRequest as AgentLlmPolicyRequest,
    AgentLlmRoutingPolicyRequest as AgentLlmRoutingPolicyRequest,
    AgentMemoryBindingRequest as AgentMemoryBindingRequest,
    AgentProfileActionRequest as AgentProfileActionRequest,
    AgentRuntimePreferencesRequest as AgentRuntimePreferencesRequest,
    ExportAgentHomeRequest as ExportAgentHomeRequest,
    MigrateAgentHomeRequest as MigrateAgentHomeRequest,
    RegisterAgentProfileRequest as RegisterAgentProfileRequest,
    SyncAgentHomeRequest as SyncAgentHomeRequest,
    UpdateAgentHomeFilesRequest as UpdateAgentHomeFilesRequest,
    UpdateAgentProfileRequest as UpdateAgentProfileRequest,
)


def _identity(payload: AgentIdentityRequest) -> AgentIdentity:
    return AgentIdentity(
        display_name=payload.display_name,
        theme=payload.theme,
        emoji=payload.emoji,
        avatar=payload.avatar,
    )


def _instruction_policy(
    payload: AgentInstructionPolicyRequest,
) -> AgentInstructionPolicy:
    return AgentInstructionPolicy(
        system_prompt=payload.system_prompt,
        response_style=payload.response_style,
        thinking_default=payload.thinking_default,
        stream_by_default=payload.stream_by_default,
    )


def _llm_routing_policy(
    payload: AgentLlmRoutingPolicyRequest,
) -> AgentLlmRoutingPolicy:
    return AgentLlmRoutingPolicy(
        default_llm_id=payload.default_llm_id,
        fallback_llm_ids=tuple(payload.fallback_llm_ids),
        image_llm_id=payload.image_llm_id,
        document_llm_id=payload.document_llm_id,
    )


def _llm_policy(payload: AgentLlmPolicyRequest) -> AgentLlmPolicy:
    return AgentLlmPolicy.from_payload(payload.model_dump())


def _execution_policy(payload: AgentExecutionPolicyRequest) -> AgentExecutionPolicy:
    return AgentExecutionPolicy(
        timeout_seconds=payload.timeout_seconds,
        max_turns=payload.max_turns,
    )


def _runtime_preferences(
    payload: AgentRuntimePreferencesRequest,
) -> AgentRuntimePreferences:
    return AgentRuntimePreferences(
        home_dir=payload.home_dir,
        workdir=payload.workdir,
        workspace=payload.workspace,
        sandbox_mode=payload.sandbox_mode,
        attrs=dict(payload.attrs),
    )


def _memory_binding(payload: AgentMemoryBindingRequest) -> AgentMemoryBinding:
    return AgentMemoryBinding(
        enabled=payload.enabled,
        scope_ref=payload.scope_ref,
        access=payload.access,
    )


def register_agent_profile_input(
    payload: RegisterAgentProfileRequest,
) -> RegisterAgentProfileInput:
    return RegisterAgentProfileInput(
        id=payload.id,
        name=payload.name,
        enabled=payload.enabled,
        identity=_identity(payload.identity),
        instruction_policy=_instruction_policy(payload.instruction_policy),
        llm_routing_policy=_llm_routing_policy(payload.llm_routing_policy),
        llm_policy=_llm_policy(payload.llm_policy),
        execution_policy=_execution_policy(payload.execution_policy),
        runtime_preferences=_runtime_preferences(payload.runtime_preferences),
        memory=_memory_binding(payload.memory),
        reason=payload.reason,
        actor=payload.actor,
    )


def update_agent_profile_input(
    agent_id: str,
    payload: UpdateAgentProfileRequest,
) -> UpdateAgentProfileInput:
    updates: dict[str, object] = {}
    if payload.name is not None:
        updates["name"] = payload.name
    if payload.enabled is not None:
        updates["enabled"] = payload.enabled
    if payload.identity is not None:
        updates["identity"] = _identity(payload.identity)
    if payload.instruction_policy is not None:
        updates["instruction_policy"] = _instruction_policy(payload.instruction_policy)
    if payload.llm_routing_policy is not None:
        updates["llm_routing_policy"] = _llm_routing_policy(payload.llm_routing_policy)
    if payload.llm_policy is not None:
        updates["llm_policy"] = _llm_policy(payload.llm_policy)
    if payload.execution_policy is not None:
        updates["execution_policy"] = _execution_policy(payload.execution_policy)
    if payload.runtime_preferences is not None:
        updates["runtime_preferences"] = _runtime_preferences(
            payload.runtime_preferences,
        )
    if payload.memory is not None:
        updates["memory"] = _memory_binding(payload.memory)
    return UpdateAgentProfileInput(
        id=agent_id,
        reason=payload.reason,
        actor=payload.actor,
        **updates,
    )


def agent_profile_action_input(
    agent_id: str,
    payload: AgentProfileActionRequest | None,
) -> AgentProfileActionInput:
    return AgentProfileActionInput(
        id=agent_id,
        reason=payload.reason if payload is not None else None,
        actor=payload.actor if payload is not None else None,
    )


def migrate_agent_home_input(
    agent_id: str,
    payload: MigrateAgentHomeRequest,
) -> MigrateAgentHomeInput:
    return MigrateAgentHomeInput(
        id=agent_id,
        home_dir=payload.home_dir,
        workdir=payload.workdir,
    )


def sync_agent_home_input(agent_id: str, payload: SyncAgentHomeRequest) -> SyncAgentHomeInput:
    return SyncAgentHomeInput(
        id=agent_id,
        home_dir=payload.home_dir,
    )


def export_agent_home_input(
    agent_id: str,
    payload: ExportAgentHomeRequest,
) -> ExportAgentHomeInput:
    return ExportAgentHomeInput(
        id=agent_id,
        home_dir=payload.home_dir,
    )


def update_agent_home_files_input(
    agent_id: str,
    payload: UpdateAgentHomeFilesRequest,
) -> UpdateAgentHomeFilesInput:
    return UpdateAgentHomeFilesInput(
        id=agent_id,
        files={item.name: item.content for item in payload.files},
    )


def profile_settings_to_input(profile: object) -> RegisterAgentProfileInput:
    return agent_profile_input_from_settings(profile)
