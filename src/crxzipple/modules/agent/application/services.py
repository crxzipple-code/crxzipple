from __future__ import annotations

from typing import Any, Callable

from crxzipple.modules.agent.application.home_operations import AgentHomeOperations
from crxzipple.modules.agent.application.home_use_cases import AgentHomeUseCases
from crxzipple.modules.agent.application.home_models import (
    AgentHomeSnapshot,
    ExportAgentHomeInput,
    ExportAgentHomeResult,
    MigrateAgentHomeInput,
    MigrateAgentHomeResult,
    SyncAgentHomeInput,
    SyncAgentHomeResult,
    UpdateAgentHomeFilesInput,
)
from crxzipple.modules.agent.application.profile_models import (
    AgentProfileActionInput,
    RegisterAgentProfileInput,
    UpdateAgentProfileInput,
)
from crxzipple.modules.agent.application.profile_use_cases import AgentProfileUseCases
from crxzipple.modules.agent.application.unit_of_work import AgentUnitOfWork
from crxzipple.modules.agent.domain.entities import AgentProfile


class AgentApplicationService:
    def __init__(
        self,
        uow_factory: Callable[[], AgentUnitOfWork],
        *,
        agent_home_root: str | None = None,
        home_scaffolder: Callable[[AgentProfile], None] | None = None,
        home_migrator: (
            Callable[[str | None, str], tuple[tuple[str, ...], tuple[str, ...]]] | None
        ) = None,
        home_config_loader: Callable[[str], dict[str, object]] | None = None,
        home_config_writer: Callable[[AgentProfile, str], Any] | None = None,
        home_config_applier: (
            Callable[[AgentProfile, dict[str, object], str], AgentProfile] | None
        ) = None,
        home_profile_factory: (
            Callable[[dict[str, object], str], AgentProfile] | None
        ) = None,
        home_registry_lister: Callable[[str], tuple[tuple[str, str], ...]] | None = None,
        home_registry_resolver: Callable[[str, str], str | None] | None = None,
        home_registry_writer: Callable[[str, str, str], Any] | None = None,
        home_registry_remover: Callable[[str, str], Any] | None = None,
        home_file_reader: Callable[[str], tuple[Any, ...]] | None = None,
        home_file_writer: Callable[[str, dict[str, str]], tuple[Any, ...]] | None = None,
    ) -> None:
        self.uow_factory = uow_factory
        self._home = AgentHomeOperations(
            agent_home_root=agent_home_root,
            home_scaffolder=home_scaffolder,
            home_migrator=home_migrator,
            home_config_loader=home_config_loader,
            home_config_writer=home_config_writer,
            home_config_applier=home_config_applier,
            home_profile_factory=home_profile_factory,
            home_registry_lister=home_registry_lister,
            home_registry_resolver=home_registry_resolver,
            home_registry_writer=home_registry_writer,
            home_registry_remover=home_registry_remover,
            home_file_reader=home_file_reader,
            home_file_writer=home_file_writer,
        )
        self.agent_home_root = self._home.agent_home_root

    def register_profile(self, data: RegisterAgentProfileInput) -> AgentProfile:
        return self._profile_use_cases().register_profile(data)

    def sync_profiles(
        self,
        profiles: tuple[RegisterAgentProfileInput, ...],
        *,
        write_home: bool | str = True,
    ) -> list[AgentProfile]:
        return self._profile_use_cases().sync_profiles(
            profiles,
            write_home=write_home,
        )

    def update_profile(self, data: UpdateAgentProfileInput) -> AgentProfile:
        return self._profile_use_cases().update_profile(data)

    def get_profile(self, profile_id: str) -> AgentProfile:
        return self._profile_use_cases().get_profile(profile_id)

    def list_profiles(self) -> list[AgentProfile]:
        return self._profile_use_cases().list_profiles()

    def resolve_registered_home(self, profile_id: str) -> str | None:
        return self._profile_use_cases().resolve_registered_home(profile_id)

    def enable_profile(
        self,
        profile: str | AgentProfileActionInput,
        *,
        reason: str | None = None,
        actor: str | None = None,
    ) -> AgentProfile:
        return self._profile_use_cases().enable_profile(
            profile,
            reason=reason,
            actor=actor,
        )

    def disable_profile(
        self,
        profile: str | AgentProfileActionInput,
        *,
        reason: str | None = None,
        actor: str | None = None,
    ) -> AgentProfile:
        return self._profile_use_cases().disable_profile(
            profile,
            reason=reason,
            actor=actor,
        )

    def delete_profile(
        self,
        profile: str | AgentProfileActionInput,
        *,
        reason: str | None = None,
        actor: str | None = None,
    ) -> None:
        self._profile_use_cases().delete_profile(
            profile,
            reason=reason,
            actor=actor,
        )

    def migrate_profile_home(
        self,
        data: MigrateAgentHomeInput,
    ) -> MigrateAgentHomeResult:
        return self._home_use_cases().migrate_profile_home(data)

    def sync_profile_home(
        self,
        data: SyncAgentHomeInput,
    ) -> SyncAgentHomeResult:
        return self._home_use_cases().sync_profile_home(data)

    def export_profile_home(
        self,
        data: ExportAgentHomeInput,
    ) -> ExportAgentHomeResult:
        return self._home_use_cases().export_profile_home(data)

    def inspect_profile_home(self, profile_id: str) -> AgentHomeSnapshot:
        return self._home_use_cases().inspect_profile_home(profile_id)

    def update_profile_home_files(
        self,
        data: UpdateAgentHomeFilesInput,
    ) -> AgentHomeSnapshot:
        return self._home_use_cases().update_profile_home_files(data)

    def _profile_use_cases(self) -> AgentProfileUseCases:
        return AgentProfileUseCases(
            uow_factory=self.uow_factory,
            home=self._home,
            agent_home_root=self.agent_home_root,
        )

    def _home_use_cases(self) -> AgentHomeUseCases:
        return AgentHomeUseCases(
            uow_factory=self.uow_factory,
            home=self._home,
            agent_home_root=self.agent_home_root,
        )
