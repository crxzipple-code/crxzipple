from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from crxzipple.modules.agent.domain.entities import AgentProfile
from crxzipple.modules.agent.domain.exceptions import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
    AgentValidationError,
)
from crxzipple.modules.agent.domain.value_objects import (
    AgentExecutionPolicy,
    AgentIdentity,
    AgentInstructionPolicy,
    AgentLlmRoutingPolicy,
    AgentMemoryBinding,
    AgentRuntimePreferences,
)
from crxzipple.shared.domain.aggregates import AggregateRoot
from crxzipple.shared.domain.events import Event


_UNSET = object()


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
    name: object = _UNSET
    enabled: object = _UNSET
    identity: object = _UNSET
    instruction_policy: object = _UNSET
    llm_routing_policy: object = _UNSET
    execution_policy: object = _UNSET
    runtime_preferences: object = _UNSET
    memory: object = _UNSET
    reason: str | None = None
    actor: str | None = None


@dataclass(frozen=True, slots=True)
class AgentProfileActionInput:
    id: str
    reason: str | None = None
    actor: str | None = None


@dataclass(frozen=True, slots=True)
class MigrateAgentHomeInput:
    id: str
    home_dir: str
    workdir: str | None = None


@dataclass(frozen=True, slots=True)
class MigrateAgentHomeResult:
    profile: AgentProfile
    source_dir: str | None
    copied_paths: tuple[str, ...] = ()
    skipped_paths: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SyncAgentHomeInput:
    id: str
    home_dir: str | None = None


@dataclass(frozen=True, slots=True)
class SyncAgentHomeResult:
    profile: AgentProfile
    home_dir: str
    path: str


@dataclass(frozen=True, slots=True)
class ExportAgentHomeInput:
    id: str
    home_dir: str | None = None


@dataclass(frozen=True, slots=True)
class ExportAgentHomeResult:
    profile: AgentProfile
    home_dir: str
    path: str


@dataclass(frozen=True, slots=True)
class AgentHomeFileSnapshot:
    name: str
    path: str
    exists: bool
    language: str
    content: str


@dataclass(frozen=True, slots=True)
class AgentHomeSnapshot:
    profile: AgentProfile
    home_dir: str
    workdir: str | None
    files: tuple[AgentHomeFileSnapshot, ...]


@dataclass(frozen=True, slots=True)
class UpdateAgentHomeFilesInput:
    id: str
    files: dict[str, str]


class AgentUnitOfWork(Protocol):
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
        self.agent_home_root = agent_home_root.strip() if agent_home_root else None
        self.home_scaffolder = home_scaffolder
        self.home_migrator = home_migrator
        self.home_config_loader = home_config_loader
        self.home_config_writer = home_config_writer
        self.home_config_applier = home_config_applier
        self.home_profile_factory = home_profile_factory
        self.home_registry_lister = home_registry_lister
        self.home_registry_resolver = home_registry_resolver
        self.home_registry_writer = home_registry_writer
        self.home_registry_remover = home_registry_remover
        self.home_file_reader = home_file_reader
        self.home_file_writer = home_file_writer

    def register_profile(self, data: RegisterAgentProfileInput) -> AgentProfile:
        with self.uow_factory() as uow:
            if self._load_home_profile(data.id) is not None:
                raise AgentAlreadyExistsError(
                    f"Agent profile '{data.id}' already exists.",
                )

            profile = AgentProfile(
                id=data.id,
                name=data.name,
                enabled=data.enabled,
                identity=data.identity,
                instruction_policy=data.instruction_policy,
                llm_routing_policy=data.llm_routing_policy,
                execution_policy=data.execution_policy,
                runtime_preferences=self._normalize_runtime_preferences(
                    data.id,
                    data.runtime_preferences,
                ),
                memory=data.memory,
            )
            profile.record_event(
                Event(
                    name="agent.profile.registered",
                    payload=_agent_profile_event_payload(
                        profile,
                        reason=data.reason,
                        actor=data.actor,
                    ),
                ),
            )
            self._persist_profile_state_and_home(
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
        with self.uow_factory() as uow:
            for data in profiles:
                existing = self._load_home_profile(data.id)
                profile_kwargs: dict[str, object] = {
                    "id": data.id,
                    "name": data.name,
                    "enabled": data.enabled,
                    "identity": data.identity,
                    "instruction_policy": data.instruction_policy,
                    "llm_routing_policy": data.llm_routing_policy,
                    "execution_policy": data.execution_policy,
                    "runtime_preferences": self._normalize_runtime_preferences(
                        data.id,
                        data.runtime_preferences,
                    ),
                    "memory": data.memory,
                }
                if existing is not None:
                    profile_kwargs["created_at"] = existing.created_at
                profile = AgentProfile(**profile_kwargs)
                profile.record_event(
                    Event(
                        name=(
                            "agent.profile.registered"
                            if existing is None
                            else "agent.profile.updated"
                        ),
                        payload=_agent_profile_event_payload(
                            profile,
                            reason=data.reason,
                            actor=data.actor,
                        ),
                    ),
                )
                self._persist_profile_state_and_home(
                    uow,
                    profile,
                    write_home=write_home,
                )
                synced_profiles.append(profile)

            uow.commit()
            return synced_profiles

    def update_profile(self, data: UpdateAgentProfileInput) -> AgentProfile:
        with self.uow_factory() as uow:
            profile = self._load_profile_for_mutation(data.id)
            if profile is None:
                raise AgentNotFoundError(
                    f"Agent profile '{data.id}' was not found.",
                )
            profile.apply_updates(
                name=data.name if data.name is not _UNSET else None,
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
                memory=data.memory if data.memory is not _UNSET else None,
                reason=data.reason,
                actor=data.actor,
            )
            self._normalize_profile_runtime_preferences(profile)
            self._persist_profile_state_and_home(
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
        for profile_id, _home_dir in sorted(self._list_registered_homes()):
            profile = self._load_home_profile(profile_id)
            if profile is not None:
                profiles.append(profile)
        return profiles

    def resolve_registered_home(self, profile_id: str) -> str | None:
        return self._resolve_registered_home(profile_id)

    def enable_profile(
        self,
        profile: str | AgentProfileActionInput,
        *,
        reason: str | None = None,
        actor: str | None = None,
    ) -> AgentProfile:
        data = _coerce_action_input(profile, reason=reason, actor=actor)
        with self.uow_factory() as uow:
            loaded_profile = self._load_profile_for_mutation(data.id)
            if loaded_profile is None:
                raise AgentNotFoundError(
                    f"Agent profile '{data.id}' was not found.",
                )
            loaded_profile.enable(reason=data.reason, actor=data.actor)
            self._persist_profile_state_and_home(uow, loaded_profile)
            uow.commit()
            return loaded_profile

    def disable_profile(
        self,
        profile: str | AgentProfileActionInput,
        *,
        reason: str | None = None,
        actor: str | None = None,
    ) -> AgentProfile:
        data = _coerce_action_input(profile, reason=reason, actor=actor)
        with self.uow_factory() as uow:
            loaded_profile = self._load_profile_for_mutation(data.id)
            if loaded_profile is None:
                raise AgentNotFoundError(
                    f"Agent profile '{data.id}' was not found.",
                )
            loaded_profile.disable(reason=data.reason, actor=data.actor)
            self._persist_profile_state_and_home(uow, loaded_profile)
            uow.commit()
            return loaded_profile

    def delete_profile(
        self,
        profile: str | AgentProfileActionInput,
        *,
        reason: str | None = None,
        actor: str | None = None,
    ) -> None:
        data = _coerce_action_input(profile, reason=reason, actor=actor)
        with self.uow_factory() as uow:
            loaded_profile = self._load_profile_for_mutation(data.id)
            if loaded_profile is None:
                raise AgentNotFoundError(
                    f"Agent profile '{data.id}' was not found.",
                )
            home_dir = loaded_profile.runtime_preferences.resolved_home_dir
            loaded_profile.record_event(
                Event(
                    name="agent.profile.deleted",
                    payload=_agent_profile_event_payload(
                        loaded_profile,
                        reason=data.reason,
                        actor=data.actor,
                    ),
                ),
            )
            uow.collect(loaded_profile)
            self._unregister_home(loaded_profile.id)
            if home_dir is not None:
                self._remove_home_config(home_dir)
            uow.commit()

    def migrate_profile_home(
        self,
        data: MigrateAgentHomeInput,
    ) -> MigrateAgentHomeResult:
        target_home_dir = data.home_dir.strip()
        if not target_home_dir:
            raise AgentValidationError("Agent home_dir cannot be empty.")

        with self.uow_factory() as uow:
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
            copied_paths, skipped_paths = self._migrate_home_contents(
                source_dir=source_dir,
                target_home_dir=target_home_dir,
            )
            self._persist_profile_state_and_home(
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
        with self.uow_factory() as uow:
            profile = self._load_profile_for_mutation(data.id)
            if profile is None:
                raise AgentNotFoundError(
                    f"Agent profile '{data.id}' was not found.",
                )

            home_dir = self._resolve_required_home_dir(
                profile=profile,
                home_dir=data.home_dir,
            )
            payload = self._load_home_config(home_dir)
            updated_profile = self._apply_home_config(
                profile,
                payload=payload,
                home_dir=home_dir,
            )
            self._normalize_profile_runtime_preferences(updated_profile)
            self._persist_profile_state_and_home(
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
        with self.uow_factory() as uow:
            profile = self._load_profile_for_mutation(data.id)
            if profile is None:
                raise AgentNotFoundError(
                    f"Agent profile '{data.id}' was not found.",
                )

            home_dir = self._resolve_required_home_dir(
                profile=profile,
                home_dir=data.home_dir,
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
            self._persist_profile_state_and_home(
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
        profile = self.get_profile(profile_id)
        home_dir = self._resolve_required_home_dir(profile=profile, home_dir=None)
        return AgentHomeSnapshot(
            profile=profile,
            home_dir=home_dir,
            workdir=profile.runtime_preferences.resolved_workdir,
            files=self._read_home_files(home_dir),
        )

    def update_profile_home_files(
        self,
        data: UpdateAgentHomeFilesInput,
    ) -> AgentHomeSnapshot:
        profile = self.get_profile(data.id)
        home_dir = self._resolve_required_home_dir(profile=profile, home_dir=None)
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
        self._ensure_home_scaffold(profile)
        files = self._write_home_files(home_dir, data.files)
        return AgentHomeSnapshot(
            profile=profile,
            home_dir=home_dir,
            workdir=profile.runtime_preferences.resolved_workdir,
            files=files,
        )

    def _load_profile_for_mutation(
        self,
        profile_id: str,
    ) -> AgentProfile | None:
        profile = self._load_home_profile(profile_id)
        if profile is not None:
            return profile
        return None

    def _normalize_runtime_preferences(
        self,
        agent_id: str,
        runtime_preferences: AgentRuntimePreferences,
    ) -> AgentRuntimePreferences:
        resolved_home_dir = (
            runtime_preferences.home_dir
            or runtime_preferences.workspace
            or self._default_home_dir(agent_id)
        )
        resolved_workdir = (
            runtime_preferences.workdir
            or runtime_preferences.workspace
            or resolved_home_dir
        )
        return AgentRuntimePreferences(
            home_dir=resolved_home_dir,
            workdir=resolved_workdir,
            workspace=runtime_preferences.workspace,
            sandbox_mode=runtime_preferences.sandbox_mode,
            attrs=dict(runtime_preferences.attrs),
        )

    def _normalize_profile_runtime_preferences(self, profile: AgentProfile) -> None:
        normalized = self._normalize_runtime_preferences(
            profile.id,
            profile.runtime_preferences,
        )
        if normalized != profile.runtime_preferences:
            profile.apply_updates(runtime_preferences=normalized)

    def _default_home_dir(self, agent_id: str) -> str:
        root = self._require_agent_home_root().rstrip("/")
        return f"{root}/{agent_id}"

    def _require_agent_home_root(self) -> str:
        if self.agent_home_root is None or not self.agent_home_root.strip():
            raise AgentValidationError("Agent home root is not configured.")
        return self.agent_home_root

    def _list_registered_homes(self) -> tuple[tuple[str, str], ...]:
        if self.home_registry_lister is None:
            raise AgentValidationError("Agent home registry listing is unavailable.")
        return self.home_registry_lister(self._require_agent_home_root())

    def _resolve_registered_home(self, agent_id: str) -> str | None:
        if self.home_registry_resolver is None:
            raise AgentValidationError("Agent home registry lookup is unavailable.")
        return self.home_registry_resolver(self._require_agent_home_root(), agent_id)

    def _register_home(self, agent_id: str, home_dir: str) -> None:
        if self.home_registry_writer is None:
            raise AgentValidationError("Agent home registry writing is unavailable.")
        self.home_registry_writer(self._require_agent_home_root(), agent_id, home_dir)

    def _unregister_home(self, agent_id: str) -> None:
        if self.home_registry_remover is None:
            raise AgentValidationError("Agent home registry removal is unavailable.")
        self.home_registry_remover(self._require_agent_home_root(), agent_id)

    def _remove_home_config(self, home_dir: str) -> None:
        config_path = Path(home_dir).expanduser() / "agent.json"
        try:
            config_path.unlink(missing_ok=True)
        except OSError as exc:
            raise AgentValidationError(
                f"Unable to remove Agent home config '{config_path}'.",
            ) from exc

    def _load_home_profile(self, profile_id: str) -> AgentProfile | None:
        home_dir = self._resolve_registered_home(profile_id)
        if home_dir is None:
            return None
        payload = self._load_home_config(home_dir)
        if self.home_profile_factory is None:
            raise AgentValidationError("Agent home profile loading is unavailable.")
        profile = self.home_profile_factory(payload, home_dir)
        if profile.id != profile_id:
            raise AgentValidationError(
                f"Agent home config id '{profile.id}' does not match requested agent '{profile_id}'.",
            )
        self._normalize_profile_runtime_preferences(profile)
        return profile

    def _persist_profile_state_and_home(
        self,
        uow: AgentUnitOfWork,
        profile: AgentProfile,
        *,
        write_home: bool | str = True,
    ) -> None:
        self._normalize_profile_runtime_preferences(profile)
        home_dir = self._resolve_agent_home_dir(profile=profile, home_dir=None)
        if home_dir is None:
            raise AgentValidationError(
                f"Agent profile '{profile.id}' must define a home directory.",
        )
        should_write_home = bool(write_home)
        if write_home == "if_missing":
            should_write_home = not Path(home_dir, "agent.json").exists()
        if should_write_home:
            self._ensure_home_scaffold(profile)
            self._write_home_config(profile, home_dir=home_dir)
        self._register_home(profile.id, home_dir)
        uow.collect(profile)

    def _ensure_home_scaffold(self, profile: AgentProfile) -> None:
        if self.home_scaffolder is None:
            return
        self.home_scaffolder(profile)

    def _migrate_home_contents(
        self,
        *,
        source_dir: str | None,
        target_home_dir: str,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        if self.home_migrator is None:
            return (), ()
        return self.home_migrator(source_dir, target_home_dir)

    def _resolve_agent_home_dir(
        self,
        *,
        profile: AgentProfile,
        home_dir: str | None,
    ) -> str | None:
        resolved_home_dir = (
            home_dir.strip()
            if home_dir is not None and home_dir.strip()
            else profile.runtime_preferences.home_dir
        )
        if resolved_home_dir is None or not resolved_home_dir.strip():
            return None
        return resolved_home_dir

    def _resolve_required_home_dir(
        self,
        *,
        profile: AgentProfile,
        home_dir: str | None,
    ) -> str:
        resolved = self._resolve_agent_home_dir(profile=profile, home_dir=home_dir)
        if resolved is not None:
            return resolved
        return self._default_home_dir(profile.id)

    def _load_home_config(self, home_dir: str) -> dict[str, object]:
        if self.home_config_loader is None:
            raise AgentValidationError("Agent home config loading is unavailable.")
        return self.home_config_loader(f"{home_dir.rstrip('/')}/agent.json")

    def _write_home_config(self, profile: AgentProfile, *, home_dir: str) -> Any:
        if self.home_config_writer is None:
            raise AgentValidationError("Agent home config writing is unavailable.")
        return self.home_config_writer(profile, home_dir)

    def _apply_home_config(
        self,
        profile: AgentProfile,
        *,
        payload: dict[str, object],
        home_dir: str,
    ) -> AgentProfile:
        if self.home_config_applier is None:
            raise AgentValidationError("Agent home config syncing is unavailable.")
        return self.home_config_applier(profile, payload, home_dir)

    def _read_home_files(self, home_dir: str) -> tuple[AgentHomeFileSnapshot, ...]:
        if self.home_file_reader is None:
            raise AgentValidationError("Agent home file reading is unavailable.")
        return tuple(
            AgentHomeFileSnapshot(
                name=item.name,
                path=item.path,
                exists=item.exists,
                language=item.language,
                content=item.content,
            )
            for item in self.home_file_reader(home_dir)
        )

    def _write_home_files(
        self,
        home_dir: str,
        files: dict[str, str],
    ) -> tuple[AgentHomeFileSnapshot, ...]:
        if self.home_file_writer is None:
            raise AgentValidationError("Agent home file writing is unavailable.")
        try:
            written_files = self.home_file_writer(home_dir, files)
        except ValueError as exc:
            raise AgentValidationError(str(exc)) from exc
        return tuple(
            AgentHomeFileSnapshot(
                name=item.name,
                path=item.path,
                exists=item.exists,
                language=item.language,
                content=item.content,
            )
            for item in written_files
        )

def _coerce_action_input(
    profile: str | AgentProfileActionInput,
    *,
    reason: str | None,
    actor: str | None,
) -> AgentProfileActionInput:
    if isinstance(profile, AgentProfileActionInput):
        return AgentProfileActionInput(
            id=profile.id,
            reason=profile.reason if profile.reason is not None else reason,
            actor=profile.actor if profile.actor is not None else actor,
        )
    return AgentProfileActionInput(id=profile, reason=reason, actor=actor)


def _agent_profile_event_payload(
    profile: AgentProfile,
    *,
    reason: str | None = None,
    actor: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "agent_profile_id": profile.id,
        "agent_profile_name": profile.name,
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
