from __future__ import annotations

from dataclasses import dataclass, field

from crxzipple.modules.agent.domain.exceptions import AgentValidationError
from crxzipple.modules.agent.domain.value_objects import (
    AgentExecutionPolicy,
    AgentIdentity,
    AgentInstructionPolicy,
    AgentLlmRoutingPolicy,
    AgentRuntimePreferences,
)
from crxzipple.shared.domain import AggregateRoot
from crxzipple.shared.domain.events import DomainEvent


@dataclass(kw_only=True)
class AgentProfile(AggregateRoot[str]):
    name: str
    description: str = ""
    enabled: bool = True
    identity: AgentIdentity = field(default_factory=AgentIdentity)
    instruction_policy: AgentInstructionPolicy = field(
        default_factory=AgentInstructionPolicy,
    )
    llm_routing_policy: AgentLlmRoutingPolicy
    execution_policy: AgentExecutionPolicy = field(default_factory=AgentExecutionPolicy)
    runtime_preferences: AgentRuntimePreferences = field(
        default_factory=AgentRuntimePreferences,
    )

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise AgentValidationError("Agent profile name cannot be empty.")
        if not self.llm_routing_policy.default_llm_id.strip():
            raise AgentValidationError(
                "Agent profile default_llm_id cannot be empty.",
            )
        if self.execution_policy.timeout_seconds <= 0:
            raise AgentValidationError(
                "Agent profile timeout_seconds must be greater than zero.",
            )
        if self.execution_policy.max_turns <= 0:
            raise AgentValidationError(
                "Agent profile max_turns must be greater than zero.",
            )
        self.description = self.description.strip()

    def apply_updates(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
        enabled: bool | None = None,
        identity: AgentIdentity | None = None,
        instruction_policy: AgentInstructionPolicy | None = None,
        llm_routing_policy: AgentLlmRoutingPolicy | None = None,
        execution_policy: AgentExecutionPolicy | None = None,
        runtime_preferences: AgentRuntimePreferences | None = None,
    ) -> None:
        if name is not None:
            if not name.strip():
                raise AgentValidationError("Agent profile name cannot be empty.")
            self.name = name
        if description is not None:
            self.description = description.strip()
        if enabled is not None:
            self.enabled = enabled
        if identity is not None:
            self.identity = identity
        if instruction_policy is not None:
            self.instruction_policy = instruction_policy
        if llm_routing_policy is not None:
            if not llm_routing_policy.default_llm_id.strip():
                raise AgentValidationError(
                    "Agent profile default_llm_id cannot be empty.",
                )
            self.llm_routing_policy = llm_routing_policy
        if execution_policy is not None:
            if execution_policy.timeout_seconds <= 0:
                raise AgentValidationError(
                    "Agent profile timeout_seconds must be greater than zero.",
                )
            if execution_policy.max_turns <= 0:
                raise AgentValidationError(
                    "Agent profile max_turns must be greater than zero.",
                )
            self.execution_policy = execution_policy
        if runtime_preferences is not None:
            self.runtime_preferences = runtime_preferences
        self.record_event(
            DomainEvent(
                name="agent.profile.updated",
                payload={"agent_profile_id": self.id, "agent_profile_name": self.name},
            ),
        )

    def enable(self) -> bool:
        if self.enabled:
            return False
        self.enabled = True
        self.record_event(
            DomainEvent(
                name="agent.profile.enabled",
                payload={"agent_profile_id": self.id, "agent_profile_name": self.name},
            ),
        )
        return True

    def disable(self) -> bool:
        if not self.enabled:
            return False
        self.enabled = False
        self.record_event(
            DomainEvent(
                name="agent.profile.disabled",
                payload={"agent_profile_id": self.id, "agent_profile_name": self.name},
            ),
        )
        return True
