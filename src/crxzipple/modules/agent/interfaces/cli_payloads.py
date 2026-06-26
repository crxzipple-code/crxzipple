from __future__ import annotations

from crxzipple.modules.agent.application.profile_models import (
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
    AgentLlmRoutingPolicy,
    AgentMemoryBinding,
    AgentRuntimePreferences,
)


def register_profile_input(
    *,
    agent_id: str,
    name: str,
    enabled: bool,
    default_llm_id: str,
    fallback_llm_id: list[str] | None,
    image_llm_id: str | None,
    document_llm_id: str | None,
    system_prompt: str,
    response_style: str | None,
    thinking_default: str | None,
    stream_by_default: bool,
    timeout_seconds: int,
    max_turns: int,
    home_dir: str | None,
    workdir: str | None,
    workspace: str | None,
    sandbox_mode: str | None,
    memory_scope_ref: str | None,
    memory_enabled: bool,
    memory_access: str,
    display_name: str | None,
    theme: str | None,
    emoji: str | None,
    avatar: str | None,
) -> RegisterAgentProfileInput:
    return RegisterAgentProfileInput(
        id=agent_id,
        name=name,
        enabled=enabled,
        identity=AgentIdentity(
            display_name=display_name,
            theme=theme,
            emoji=emoji,
            avatar=avatar,
        ),
        instruction_policy=AgentInstructionPolicy(
            system_prompt=system_prompt,
            response_style=response_style,
            thinking_default=thinking_default,
            stream_by_default=stream_by_default,
        ),
        llm_routing_policy=AgentLlmRoutingPolicy(
            default_llm_id=default_llm_id,
            fallback_llm_ids=tuple(fallback_llm_id or ()),
            image_llm_id=image_llm_id,
            document_llm_id=document_llm_id,
        ),
        execution_policy=AgentExecutionPolicy(
            timeout_seconds=timeout_seconds,
            max_turns=max_turns,
        ),
        runtime_preferences=AgentRuntimePreferences(
            home_dir=home_dir,
            workdir=workdir,
            workspace=workspace,
            sandbox_mode=sandbox_mode,
        ),
        memory=AgentMemoryBinding(
            enabled=memory_enabled,
            scope_ref=memory_scope_ref,
            access=memory_access,
        ),
    )


def update_profile_input(
    *,
    agent_id: str,
    name: str | None,
    default_llm_id: str | None,
    memory_scope_ref: str | None,
    memory_enabled: bool | None,
    memory_access: str | None,
    current_memory: AgentMemoryBinding | None,
) -> UpdateAgentProfileInput:
    updates: dict[str, object] = {}
    if name is not None:
        updates["name"] = name
    if default_llm_id is not None:
        updates["llm_routing_policy"] = AgentLlmRoutingPolicy(
            default_llm_id=default_llm_id,
        )
    if (
        memory_scope_ref is not None
        or memory_enabled is not None
        or memory_access is not None
    ):
        if current_memory is None:
            raise ValueError("current memory binding is required for memory updates.")
        updates["memory"] = AgentMemoryBinding(
            enabled=(
                memory_enabled
                if memory_enabled is not None
                else current_memory.enabled
            ),
            scope_ref=(
                memory_scope_ref
                if memory_scope_ref is not None
                else current_memory.scope_ref
            ),
            access=memory_access or current_memory.access,
        )
    return UpdateAgentProfileInput(id=agent_id, **updates)


def profile_settings_to_input(profile: object) -> RegisterAgentProfileInput:
    return agent_profile_input_from_settings(profile)
