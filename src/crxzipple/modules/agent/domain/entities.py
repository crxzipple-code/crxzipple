from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from crxzipple.modules.agent.domain.exceptions import AgentValidationError
from crxzipple.modules.agent.domain.value_objects import (
    AgentExecutionPolicy,
    AgentIdentity,
    AgentInstructionPolicy,
    AgentLlmRoutingPolicy,
    AgentMemoryBinding,
    AgentRuntimePreferences,
)
from crxzipple.shared.domain import AggregateRoot
from crxzipple.shared.domain.events import Event
from crxzipple.shared.time import coerce_utc_datetime


@dataclass(kw_only=True)
class AgentProfile(AggregateRoot[str]):
    name: str
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
    memory: AgentMemoryBinding = field(default_factory=AgentMemoryBinding)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
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
        self.created_at = coerce_utc_datetime(self.created_at)
        self.updated_at = coerce_utc_datetime(self.updated_at)

    def apply_updates(
        self,
        *,
        name: str | None = None,
        enabled: bool | None = None,
        identity: AgentIdentity | None = None,
        instruction_policy: AgentInstructionPolicy | None = None,
        llm_routing_policy: AgentLlmRoutingPolicy | None = None,
        execution_policy: AgentExecutionPolicy | None = None,
        runtime_preferences: AgentRuntimePreferences | None = None,
        memory: AgentMemoryBinding | None = None,
        reason: str | None = None,
        actor: str | None = None,
    ) -> None:
        if name is not None:
            if not name.strip():
                raise AgentValidationError("Agent profile name cannot be empty.")
            self.name = name
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
        if memory is not None:
            self.memory = memory
        self.updated_at = datetime.now(timezone.utc)
        self.record_event(
            Event(
                name="agent.profile.updated",
                payload=self._event_payload(reason=reason, actor=actor),
            ),
        )

    def enable(self, *, reason: str | None = None, actor: str | None = None) -> bool:
        if self.enabled:
            return False
        self.enabled = True
        self.updated_at = datetime.now(timezone.utc)
        self.record_event(
            Event(
                name="agent.profile.enabled",
                payload=self._event_payload(reason=reason, actor=actor),
            ),
        )
        return True

    def disable(self, *, reason: str | None = None, actor: str | None = None) -> bool:
        if not self.enabled:
            return False
        self.enabled = False
        self.updated_at = datetime.now(timezone.utc)
        self.record_event(
            Event(
                name="agent.profile.disabled",
                payload=self._event_payload(reason=reason, actor=actor),
            ),
        )
        return True

    def _event_payload(
        self,
        *,
        reason: str | None = None,
        actor: str | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "agent_profile_id": self.id,
            "agent_profile_name": self.name,
        }
        normalized_reason = _normalize_optional_text(reason)
        normalized_actor = _normalize_optional_text(actor)
        if normalized_reason is not None:
            payload["reason"] = normalized_reason
        if normalized_actor is not None:
            payload["actor"] = normalized_actor
        return payload


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
