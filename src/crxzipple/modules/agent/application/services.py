from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from crxzipple.modules.agent.domain.entities import AgentProfile
from crxzipple.modules.agent.domain.exceptions import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
)
from crxzipple.modules.agent.domain.repositories import AgentProfileRepository
from crxzipple.modules.agent.domain.value_objects import (
    AgentExecutionPolicy,
    AgentIdentity,
    AgentInstructionPolicy,
    AgentLlmRoutingPolicy,
    AgentRuntimePreferences,
)
from crxzipple.shared.domain.aggregates import AggregateRoot
from crxzipple.shared.domain.events import DomainEvent


_UNSET = object()


@dataclass(frozen=True, slots=True)
class RegisterAgentProfileInput:
    id: str
    name: str
    description: str = ""
    enabled: bool = True
    identity: AgentIdentity = field(default_factory=AgentIdentity)
    instruction_policy: AgentInstructionPolicy = field(
        default_factory=AgentInstructionPolicy,
    )
    llm_routing_policy: AgentLlmRoutingPolicy = field(
        default_factory=lambda: AgentLlmRoutingPolicy(default_llm_id=""),
    )
    execution_policy: AgentExecutionPolicy = field(default_factory=AgentExecutionPolicy)
    runtime_preferences: AgentRuntimePreferences = field(
        default_factory=AgentRuntimePreferences,
    )


@dataclass(frozen=True, slots=True)
class UpdateAgentProfileInput:
    id: str
    name: object = _UNSET
    description: object = _UNSET
    enabled: object = _UNSET
    identity: object = _UNSET
    instruction_policy: object = _UNSET
    llm_routing_policy: object = _UNSET
    execution_policy: object = _UNSET
    runtime_preferences: object = _UNSET


class AgentUnitOfWork(Protocol):
    agent_profiles: AgentProfileRepository

    def __enter__(self) -> "AgentUnitOfWork":
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        ...

    def collect(self, aggregate: AggregateRoot[Any]) -> None:
        ...

    def commit(self) -> None:
        ...

    def rollback(self) -> None:
        ...


class AgentApplicationService:
    def __init__(self, uow_factory: Callable[[], AgentUnitOfWork]) -> None:
        self.uow_factory = uow_factory

    def register_profile(self, data: RegisterAgentProfileInput) -> AgentProfile:
        with self.uow_factory() as uow:
            existing = uow.agent_profiles.get(data.id)
            if existing is not None:
                raise AgentAlreadyExistsError(
                    f"Agent profile '{data.id}' already exists.",
                )

            profile = AgentProfile(
                id=data.id,
                name=data.name,
                description=data.description,
                enabled=data.enabled,
                identity=data.identity,
                instruction_policy=data.instruction_policy,
                llm_routing_policy=data.llm_routing_policy,
                execution_policy=data.execution_policy,
                runtime_preferences=data.runtime_preferences,
            )
            profile.record_event(
                DomainEvent(
                    name="agent.profile.registered",
                    payload={
                        "agent_profile_id": profile.id,
                        "agent_profile_name": profile.name,
                    },
                ),
            )
            uow.agent_profiles.add(profile)
            uow.collect(profile)
            uow.commit()
            return profile

    def sync_profiles(
        self,
        profiles: tuple[RegisterAgentProfileInput, ...],
    ) -> list[AgentProfile]:
        if not profiles:
            return []

        synced_profiles: list[AgentProfile] = []
        with self.uow_factory() as uow:
            for data in profiles:
                existing = uow.agent_profiles.get(data.id)
                profile = AgentProfile(
                    id=data.id,
                    name=data.name,
                    description=data.description,
                    enabled=data.enabled,
                    identity=data.identity,
                    instruction_policy=data.instruction_policy,
                    llm_routing_policy=data.llm_routing_policy,
                    execution_policy=data.execution_policy,
                    runtime_preferences=data.runtime_preferences,
                )
                profile.record_event(
                    DomainEvent(
                        name=(
                            "agent.profile.registered"
                            if existing is None
                            else "agent.profile.updated"
                        ),
                        payload={
                            "agent_profile_id": profile.id,
                            "agent_profile_name": profile.name,
                        },
                    ),
                )
                uow.agent_profiles.add(profile)
                uow.collect(profile)
                synced_profiles.append(profile)

            uow.commit()
            return synced_profiles

    def update_profile(self, data: UpdateAgentProfileInput) -> AgentProfile:
        with self.uow_factory() as uow:
            profile = uow.agent_profiles.get(data.id)
            if profile is None:
                raise AgentNotFoundError(
                    f"Agent profile '{data.id}' was not found.",
                )
            profile.apply_updates(
                name=data.name if data.name is not _UNSET else None,
                description=(
                    data.description if data.description is not _UNSET else None
                ),
                enabled=data.enabled if data.enabled is not _UNSET else None,
                identity=data.identity if data.identity is not _UNSET else None,
                instruction_policy=(
                    data.instruction_policy
                    if data.instruction_policy is not _UNSET
                    else None
                ),
                llm_routing_policy=(
                    data.llm_routing_policy
                    if data.llm_routing_policy is not _UNSET
                    else None
                ),
                execution_policy=(
                    data.execution_policy
                    if data.execution_policy is not _UNSET
                    else None
                ),
                runtime_preferences=(
                    data.runtime_preferences
                    if data.runtime_preferences is not _UNSET
                    else None
                ),
            )
            uow.agent_profiles.add(profile)
            uow.collect(profile)
            uow.commit()
            return profile

    def get_profile(self, profile_id: str) -> AgentProfile:
        with self.uow_factory() as uow:
            profile = uow.agent_profiles.get(profile_id)
            if profile is None:
                raise AgentNotFoundError(
                    f"Agent profile '{profile_id}' was not found.",
                )
            return profile

    def list_profiles(self) -> list[AgentProfile]:
        with self.uow_factory() as uow:
            return uow.agent_profiles.list()

    def enable_profile(self, profile_id: str) -> AgentProfile:
        with self.uow_factory() as uow:
            profile = uow.agent_profiles.get(profile_id)
            if profile is None:
                raise AgentNotFoundError(
                    f"Agent profile '{profile_id}' was not found.",
                )
            profile.enable()
            uow.agent_profiles.add(profile)
            uow.collect(profile)
            uow.commit()
            return profile

    def disable_profile(self, profile_id: str) -> AgentProfile:
        with self.uow_factory() as uow:
            profile = uow.agent_profiles.get(profile_id)
            if profile is None:
                raise AgentNotFoundError(
                    f"Agent profile '{profile_id}' was not found.",
                )
            profile.disable()
            uow.agent_profiles.add(profile)
            uow.collect(profile)
            uow.commit()
            return profile
