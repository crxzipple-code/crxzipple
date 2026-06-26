from __future__ import annotations

from dataclasses import dataclass, field

from crxzipple.modules.agent.domain.value_objects import (
    AgentExecutionPolicy,
    AgentIdentity,
    AgentInstructionPolicy,
    AgentLlmPolicy,
    AgentLlmRoutingPolicy,
    AgentMemoryBinding,
    AgentRuntimePreferences,
)


UNSET_FIELD = object()


@dataclass(frozen=True, slots=True)
class RegisterAgentProfileInput:
    id: str
    name: str
    enabled: bool = True
    identity: AgentIdentity = field(default_factory=AgentIdentity)
    instruction_policy: AgentInstructionPolicy = field(
        default_factory=AgentInstructionPolicy,
    )
    llm_routing_policy: AgentLlmRoutingPolicy = field(
        default_factory=lambda: AgentLlmRoutingPolicy(default_llm_id=""),
    )
    llm_policy: AgentLlmPolicy = field(default_factory=AgentLlmPolicy)
    execution_policy: AgentExecutionPolicy = field(default_factory=AgentExecutionPolicy)
    runtime_preferences: AgentRuntimePreferences = field(
        default_factory=AgentRuntimePreferences,
    )
    memory: AgentMemoryBinding = field(default_factory=AgentMemoryBinding)
    reason: str | None = None
    actor: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateAgentProfileInput:
    id: str
    name: object = UNSET_FIELD
    enabled: object = UNSET_FIELD
    identity: object = UNSET_FIELD
    instruction_policy: object = UNSET_FIELD
    llm_routing_policy: object = UNSET_FIELD
    llm_policy: object = UNSET_FIELD
    execution_policy: object = UNSET_FIELD
    runtime_preferences: object = UNSET_FIELD
    memory: object = UNSET_FIELD
    reason: str | None = None
    actor: str | None = None


@dataclass(frozen=True, slots=True)
class AgentProfileActionInput:
    id: str
    reason: str | None = None
    actor: str | None = None


__all__ = [
    "UNSET_FIELD",
    "AgentProfileActionInput",
    "RegisterAgentProfileInput",
    "UpdateAgentProfileInput",
]
