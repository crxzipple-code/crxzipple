from __future__ import annotations

from typing import Callable

from crxzipple.modules.agent.application.event_payloads import (
    agent_profile_event_payload,
    coerce_action_input,
)
from crxzipple.modules.agent.application.home_operations import AgentHomeOperations
from crxzipple.modules.agent.application.profile_models import (
    AgentProfileActionInput,
    RegisterAgentProfileInput,
    UpdateAgentProfileInput,
)
from crxzipple.modules.agent.application.profile_factory import (
    build_agent_profile_from_registration,
)
from crxzipple.modules.agent.application.profile_updates import profile_update_kwargs
from crxzipple.modules.agent.application.unit_of_work import AgentUnitOfWork
from crxzipple.modules.agent.domain.entities import AgentProfile
from crxzipple.modules.agent.domain.exceptions import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
)
from crxzipple.shared.domain.events import Event


class AgentProfileUseCases:
    def __init__(
        self,
        *,
        uow_factory: Callable[[], AgentUnitOfWork],
        home: AgentHomeOperations,
        agent_home_root: str | None,
    ) -> None:
        self._uow_factory = uow_factory
        self._home = home
        self._agent_home_root = agent_home_root

    def register_profile(self, data: RegisterAgentProfileInput) -> AgentProfile:
        with self._uow_factory() as uow:
            if self._load_home_profile(data.id) is not None:
                raise AgentAlreadyExistsError(
                    f"Agent profile '{data.id}' already exists.",
                )

            profile = build_agent_profile_from_registration(
                data,
                agent_home_root=self._agent_home_root,
            )
            profile.record_event(
                Event(
                    name="agent.profile.registered",
                    payload=agent_profile_event_payload(
                        profile,
                        reason=data.reason,
                        actor=data.actor,
                    ),
                ),
            )
            self._home.persist_profile_state_and_home(
                uow,
                profile,
            )
            uow.commit()
            return profile

    def sync_profiles(
        self,
        profiles: tuple[RegisterAgentProfileInput, ...],
        *,
        write_home: bool | str = True,
    ) -> list[AgentProfile]:
        if not profiles:
            return []

        synced_profiles: list[AgentProfile] = []
        with self._uow_factory() as uow:
            for data in profiles:
                existing = self._load_home_profile(data.id)
                profile = build_agent_profile_from_registration(
                    data,
                    agent_home_root=self._agent_home_root,
                    created_at=existing.created_at if existing is not None else None,
                )
                profile.record_event(
                    Event(
                        name=(
                            "agent.profile.registered"
                            if existing is None
                            else "agent.profile.updated"
                        ),
                        payload=agent_profile_event_payload(
                            profile,
                            reason=data.reason,
                            actor=data.actor,
                        ),
                    ),
                )
                self._home.persist_profile_state_and_home(
                    uow,
                    profile,
                    write_home=write_home,
                )
                synced_profiles.append(profile)

            uow.commit()
            return synced_profiles

    def update_profile(self, data: UpdateAgentProfileInput) -> AgentProfile:
        with self._uow_factory() as uow:
            profile = self._load_profile_for_mutation(data.id)
            if profile is None:
                raise AgentNotFoundError(
                    f"Agent profile '{data.id}' was not found.",
                )
            profile.apply_updates(**profile_update_kwargs(data))
            self._home.normalize_profile_runtime_preferences(profile)
            self._home.persist_profile_state_and_home(
                uow,
                profile,
            )
            uow.commit()
            return profile

    def get_profile(self, profile_id: str) -> AgentProfile:
        profile = self._load_home_profile(profile_id)
        if profile is not None:
            return profile
        raise AgentNotFoundError(
            f"Agent profile '{profile_id}' was not found.",
        )

    def list_profiles(self) -> list[AgentProfile]:
        profiles: list[AgentProfile] = []
        for profile_id, _home_dir in sorted(self._home.list_registered_homes()):
            profile = self._load_home_profile(profile_id)
            if profile is not None:
                profiles.append(profile)
        return profiles

    def resolve_registered_home(self, profile_id: str) -> str | None:
        return self._home.resolve_registered_home(profile_id)

    def enable_profile(
        self,
        profile: str | AgentProfileActionInput,
        *,
        reason: str | None = None,
        actor: str | None = None,
    ) -> AgentProfile:
        data = coerce_action_input(profile, reason=reason, actor=actor)
        with self._uow_factory() as uow:
            loaded_profile = self._load_profile_for_mutation(data.id)
            if loaded_profile is None:
                raise AgentNotFoundError(
                    f"Agent profile '{data.id}' was not found.",
                )
            loaded_profile.enable(reason=data.reason, actor=data.actor)
            self._home.persist_profile_state_and_home(uow, loaded_profile)
            uow.commit()
            return loaded_profile

    def disable_profile(
        self,
        profile: str | AgentProfileActionInput,
        *,
        reason: str | None = None,
        actor: str | None = None,
    ) -> AgentProfile:
        data = coerce_action_input(profile, reason=reason, actor=actor)
        with self._uow_factory() as uow:
            loaded_profile = self._load_profile_for_mutation(data.id)
            if loaded_profile is None:
                raise AgentNotFoundError(
                    f"Agent profile '{data.id}' was not found.",
                )
            loaded_profile.disable(reason=data.reason, actor=data.actor)
            self._home.persist_profile_state_and_home(uow, loaded_profile)
            uow.commit()
            return loaded_profile

    def delete_profile(
        self,
        profile: str | AgentProfileActionInput,
        *,
        reason: str | None = None,
        actor: str | None = None,
    ) -> None:
        data = coerce_action_input(profile, reason=reason, actor=actor)
        with self._uow_factory() as uow:
            loaded_profile = self._load_profile_for_mutation(data.id)
            if loaded_profile is None:
                raise AgentNotFoundError(
                    f"Agent profile '{data.id}' was not found.",
                )
            home_dir = loaded_profile.runtime_preferences.resolved_home_dir
            loaded_profile.record_event(
                Event(
                    name="agent.profile.deleted",
                    payload=agent_profile_event_payload(
                        loaded_profile,
                        reason=data.reason,
                        actor=data.actor,
                    ),
                ),
            )
            uow.collect(loaded_profile)
            self._home.unregister_home(loaded_profile.id)
            if home_dir is not None:
                self._home.remove_home_config(home_dir)
            uow.commit()

    def _load_profile_for_mutation(
        self,
        profile_id: str,
    ) -> AgentProfile | None:
        return self._load_home_profile(profile_id)

    def _load_home_profile(self, profile_id: str) -> AgentProfile | None:
        return self._home.load_home_profile(profile_id)
