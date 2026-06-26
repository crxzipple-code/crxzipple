from __future__ import annotations

from typing import Callable

from crxzipple.modules.agent.application.home_operations import AgentHomeOperations
from crxzipple.modules.agent.application.home_runtime import resolve_required_home_dir
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
from crxzipple.modules.agent.application.unit_of_work import AgentUnitOfWork
from crxzipple.modules.agent.domain.entities import AgentProfile
from crxzipple.modules.agent.domain.exceptions import (
    AgentNotFoundError,
    AgentValidationError,
)
from crxzipple.modules.agent.domain.value_objects import AgentRuntimePreferences


class AgentHomeUseCases:
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

    def migrate_profile_home(
        self,
        data: MigrateAgentHomeInput,
    ) -> MigrateAgentHomeResult:
        target_home_dir = data.home_dir.strip()
        if not target_home_dir:
            raise AgentValidationError("Agent home_dir cannot be empty.")

        with self._uow_factory() as uow:
            profile = self._load_profile_for_mutation(data.id)
            if profile is None:
                raise AgentNotFoundError(
                    f"Agent profile '{data.id}' was not found.",
                )

            previous_runtime_preferences = profile.runtime_preferences
            source_dir = (
                previous_runtime_preferences.workspace
                or previous_runtime_preferences.resolved_home_dir
            )
            resolved_workdir = (
                data.workdir.strip()
                if data.workdir is not None and data.workdir.strip()
                else previous_runtime_preferences.resolved_workdir
                or target_home_dir
            )
            profile.apply_updates(
                runtime_preferences=AgentRuntimePreferences(
                    home_dir=target_home_dir,
                    workdir=resolved_workdir,
                    sandbox_mode=previous_runtime_preferences.sandbox_mode,
                    attrs=dict(previous_runtime_preferences.attrs),
                ),
            )
            copied_paths, skipped_paths = self._home.migrate_home_contents(
                source_dir=source_dir,
                target_home_dir=target_home_dir,
            )
            self._home.persist_profile_state_and_home(
                uow,
                profile,
            )
            uow.commit()
            return MigrateAgentHomeResult(
                profile=profile,
                source_dir=source_dir,
                copied_paths=copied_paths,
                skipped_paths=skipped_paths,
            )

    def sync_profile_home(
        self,
        data: SyncAgentHomeInput,
    ) -> SyncAgentHomeResult:
        with self._uow_factory() as uow:
            profile = self._load_profile_for_mutation(data.id)
            if profile is None:
                raise AgentNotFoundError(
                    f"Agent profile '{data.id}' was not found.",
                )

            home_dir = resolve_required_home_dir(
                profile=profile,
                home_dir=data.home_dir,
                agent_home_root=self._agent_home_root,
            )
            payload = self._home.load_home_config(home_dir)
            updated_profile = self._home.apply_home_config(
                profile,
                payload=payload,
                home_dir=home_dir,
            )
            self._home.normalize_profile_runtime_preferences(updated_profile)
            self._home.persist_profile_state_and_home(
                uow,
                updated_profile,
            )
            uow.commit()
            return SyncAgentHomeResult(
                profile=updated_profile,
                home_dir=home_dir,
                path=f"{home_dir.rstrip('/')}/agent.json",
            )

    def export_profile_home(
        self,
        data: ExportAgentHomeInput,
    ) -> ExportAgentHomeResult:
        with self._uow_factory() as uow:
            profile = self._load_profile_for_mutation(data.id)
            if profile is None:
                raise AgentNotFoundError(
                    f"Agent profile '{data.id}' was not found.",
                )

            home_dir = resolve_required_home_dir(
                profile=profile,
                home_dir=data.home_dir,
                agent_home_root=self._agent_home_root,
            )
            if data.home_dir is not None and data.home_dir.strip():
                profile.apply_updates(
                    runtime_preferences=AgentRuntimePreferences(
                        home_dir=home_dir,
                        workdir=profile.runtime_preferences.resolved_workdir or home_dir,
                        sandbox_mode=profile.runtime_preferences.sandbox_mode,
                        attrs=dict(profile.runtime_preferences.attrs),
                    ),
                )
            self._home.persist_profile_state_and_home(
                uow,
                profile,
            )
            uow.commit()
            return ExportAgentHomeResult(
                profile=profile,
                home_dir=home_dir,
                path=f"{home_dir.rstrip('/')}/agent.json",
            )

    def inspect_profile_home(self, profile_id: str) -> AgentHomeSnapshot:
        profile = self._get_profile(profile_id)
        home_dir = resolve_required_home_dir(
            profile=profile,
            home_dir=None,
            agent_home_root=self._agent_home_root,
        )
        return AgentHomeSnapshot(
            profile=profile,
            home_dir=home_dir,
            workdir=profile.runtime_preferences.resolved_workdir,
            files=self._home.read_home_files(home_dir),
        )

    def update_profile_home_files(
        self,
        data: UpdateAgentHomeFilesInput,
    ) -> AgentHomeSnapshot:
        profile = self._get_profile(data.id)
        home_dir = resolve_required_home_dir(
            profile=profile,
            home_dir=None,
            agent_home_root=self._agent_home_root,
        )
        if profile.runtime_preferences.home_dir != home_dir:
            profile.apply_updates(
                runtime_preferences=AgentRuntimePreferences(
                    home_dir=home_dir,
                    workdir=profile.runtime_preferences.resolved_workdir or home_dir,
                    workspace=profile.runtime_preferences.workspace,
                    sandbox_mode=profile.runtime_preferences.sandbox_mode,
                    attrs=dict(profile.runtime_preferences.attrs),
                ),
            )
            self._home.ensure_home_scaffold(profile)
        files = self._home.write_home_files(home_dir, data.files)
        return AgentHomeSnapshot(
            profile=profile,
            home_dir=home_dir,
            workdir=profile.runtime_preferences.resolved_workdir,
            files=files,
        )

    def _get_profile(self, profile_id: str) -> AgentProfile:
        profile = self._load_home_profile(profile_id)
        if profile is not None:
            return profile
        raise AgentNotFoundError(
            f"Agent profile '{profile_id}' was not found.",
        )

    def _load_profile_for_mutation(
        self,
        profile_id: str,
    ) -> AgentProfile | None:
        return self._load_home_profile(profile_id)

    def _load_home_profile(self, profile_id: str) -> AgentProfile | None:
        return self._home.load_home_profile(profile_id)
