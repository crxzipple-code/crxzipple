from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.agent.domain.entities import AgentProfile
from crxzipple.modules.agent.domain.value_objects import (
    AgentExecutionPolicy,
    AgentIdentity,
    AgentInstructionPolicy,
    AgentLlmRoutingPolicy,
    AgentMemoryBinding,
    AgentRuntimePreferences,
)
from crxzipple.shared.time import format_datetime_utc


@dataclass(frozen=True, slots=True)
class AgentIdentityDTO:
    display_name: str | None
    theme: str | None
    emoji: str | None
    avatar: str | None

    @classmethod
    def from_value(cls, value: AgentIdentity) -> "AgentIdentityDTO":
        return cls(
            display_name=value.display_name,
            theme=value.theme,
            emoji=value.emoji,
            avatar=value.avatar,
        )


@dataclass(frozen=True, slots=True)
class AgentInstructionPolicyDTO:
    system_prompt: str
    response_style: str | None
    thinking_default: str | None
    stream_by_default: bool

    @classmethod
    def from_value(
        cls,
        value: AgentInstructionPolicy,
    ) -> "AgentInstructionPolicyDTO":
        return cls(
            system_prompt=value.system_prompt,
            response_style=value.response_style,
            thinking_default=value.thinking_default,
            stream_by_default=value.stream_by_default,
        )


@dataclass(frozen=True, slots=True)
class AgentLlmRoutingPolicyDTO:
    default_llm_id: str
    fallback_llm_ids: tuple[str, ...]
    image_llm_id: str | None
    document_llm_id: str | None

    @classmethod
    def from_value(
        cls,
        value: AgentLlmRoutingPolicy,
    ) -> "AgentLlmRoutingPolicyDTO":
        return cls(
            default_llm_id=value.default_llm_id,
            fallback_llm_ids=value.fallback_llm_ids,
            image_llm_id=value.image_llm_id,
            document_llm_id=value.document_llm_id,
        )


@dataclass(frozen=True, slots=True)
class AgentExecutionPolicyDTO:
    timeout_seconds: int
    max_turns: int

    @classmethod
    def from_value(
        cls,
        value: AgentExecutionPolicy,
    ) -> "AgentExecutionPolicyDTO":
        return cls(
            timeout_seconds=value.timeout_seconds,
            max_turns=value.max_turns,
        )


@dataclass(frozen=True, slots=True)
class AgentRuntimePreferencesDTO:
    home_dir: str | None
    workdir: str | None
    workspace: str | None
    sandbox_mode: str | None
    attrs: dict[str, object]

    @classmethod
    def from_value(
        cls,
        value: AgentRuntimePreferences,
    ) -> "AgentRuntimePreferencesDTO":
        return cls(
            home_dir=value.resolved_home_dir,
            workdir=value.resolved_workdir,
            workspace=value.compat_workspace,
            sandbox_mode=value.sandbox_mode,
            attrs=dict(value.attrs),
        )


@dataclass(frozen=True, slots=True)
class AgentMemoryBindingDTO:
    enabled: bool
    scope_ref: str | None
    access: str

    @classmethod
    def from_value(cls, value: AgentMemoryBinding) -> "AgentMemoryBindingDTO":
        return cls(
            enabled=value.enabled,
            scope_ref=value.scope_ref,
            access=value.access,
        )


@dataclass(frozen=True, slots=True)
class AgentProfileDTO:
    id: str
    name: str
    enabled: bool
    created_at: str
    updated_at: str
    identity: AgentIdentityDTO
    instruction_policy: AgentInstructionPolicyDTO
    llm_routing_policy: AgentLlmRoutingPolicyDTO
    execution_policy: AgentExecutionPolicyDTO
    runtime_preferences: AgentRuntimePreferencesDTO
    memory: AgentMemoryBindingDTO

    @classmethod
    def from_entity(cls, profile: AgentProfile) -> "AgentProfileDTO":
        return cls(
            id=profile.id,
            name=profile.name,
            enabled=profile.enabled,
            created_at=format_datetime_utc(profile.created_at),
            updated_at=format_datetime_utc(profile.updated_at),
            identity=AgentIdentityDTO.from_value(profile.identity),
            instruction_policy=AgentInstructionPolicyDTO.from_value(
                profile.instruction_policy,
            ),
            llm_routing_policy=AgentLlmRoutingPolicyDTO.from_value(
                profile.llm_routing_policy,
            ),
            execution_policy=AgentExecutionPolicyDTO.from_value(
                profile.execution_policy,
            ),
            runtime_preferences=AgentRuntimePreferencesDTO.from_value(
                profile.runtime_preferences,
            ),
            memory=AgentMemoryBindingDTO.from_value(profile.memory),
        )
