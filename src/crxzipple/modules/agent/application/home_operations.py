from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Protocol

from crxzipple.modules.agent.application.home_runtime import (
    normalize_runtime_preferences,
    require_agent_home_root,
    resolve_agent_home_dir,
)
from crxzipple.modules.agent.application.home_models import AgentHomeFileSnapshot
from crxzipple.modules.agent.domain.entities import AgentProfile
from crxzipple.modules.agent.domain.exceptions import AgentValidationError
from crxzipple.shared.domain.aggregates import AggregateRoot


class AgentProfileCollector(Protocol):
    def collect(self, aggregate: AggregateRoot[Any]) -> None:
        ...


class AgentHomeOperations:
    def __init__(
        self,
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
        self.agent_home_root = agent_home_root.strip() if agent_home_root else None
        self._home_scaffolder = home_scaffolder
        self._home_migrator = home_migrator
        self._home_config_loader = home_config_loader
        self._home_config_writer = home_config_writer
        self._home_config_applier = home_config_applier
        self._home_profile_factory = home_profile_factory
        self._home_registry_lister = home_registry_lister
        self._home_registry_resolver = home_registry_resolver
        self._home_registry_writer = home_registry_writer
        self._home_registry_remover = home_registry_remover
        self._home_file_reader = home_file_reader
        self._home_file_writer = home_file_writer

    def normalize_profile_runtime_preferences(self, profile: AgentProfile) -> None:
        normalized = normalize_runtime_preferences(
            profile.id,
            profile.runtime_preferences,
            agent_home_root=self.agent_home_root,
        )
        if normalized != profile.runtime_preferences:
            profile.apply_updates(runtime_preferences=normalized)

    def list_registered_homes(self) -> tuple[tuple[str, str], ...]:
        if self._home_registry_lister is None:
            raise AgentValidationError("Agent home registry listing is unavailable.")
        return self._home_registry_lister(require_agent_home_root(self.agent_home_root))

    def resolve_registered_home(self, agent_id: str) -> str | None:
        if self._home_registry_resolver is None:
            raise AgentValidationError("Agent home registry lookup is unavailable.")
        return self._home_registry_resolver(
            require_agent_home_root(self.agent_home_root),
            agent_id,
        )

    def register_home(self, agent_id: str, home_dir: str) -> None:
        if self._home_registry_writer is None:
            raise AgentValidationError("Agent home registry writing is unavailable.")
        self._home_registry_writer(
            require_agent_home_root(self.agent_home_root),
            agent_id,
            home_dir,
        )

    def unregister_home(self, agent_id: str) -> None:
        if self._home_registry_remover is None:
            raise AgentValidationError("Agent home registry removal is unavailable.")
        self._home_registry_remover(
            require_agent_home_root(self.agent_home_root),
            agent_id,
        )

    def remove_home_config(self, home_dir: str) -> None:
        config_path = Path(home_dir).expanduser() / "agent.json"
        try:
            config_path.unlink(missing_ok=True)
        except OSError as exc:
            raise AgentValidationError(
                f"Unable to remove Agent home config '{config_path}'.",
            ) from exc

    def load_home_profile(self, profile_id: str) -> AgentProfile | None:
        home_dir = self.resolve_registered_home(profile_id)
        if home_dir is None:
            return None
        payload = self.load_home_config(home_dir)
        if self._home_profile_factory is None:
            raise AgentValidationError("Agent home profile loading is unavailable.")
        profile = self._home_profile_factory(payload, home_dir)
        if profile.id != profile_id:
            raise AgentValidationError(
                f"Agent home config id '{profile.id}' does not match requested agent '{profile_id}'.",
            )
        self.normalize_profile_runtime_preferences(profile)
        return profile

    def persist_profile_state_and_home(
        self,
        collector: AgentProfileCollector,
        profile: AgentProfile,
        *,
        write_home: bool | str = True,
    ) -> None:
        self.normalize_profile_runtime_preferences(profile)
        home_dir = resolve_agent_home_dir(profile=profile, home_dir=None)
        if home_dir is None:
            raise AgentValidationError(
                f"Agent profile '{profile.id}' must define a home directory.",
            )
        should_write_home = bool(write_home)
        if write_home == "if_missing":
            should_write_home = not Path(home_dir, "agent.json").exists()
        if should_write_home:
            self.ensure_home_scaffold(profile)
            self.write_home_config(profile, home_dir=home_dir)
        self.register_home(profile.id, home_dir)
        collector.collect(profile)

    def ensure_home_scaffold(self, profile: AgentProfile) -> None:
        if self._home_scaffolder is None:
            return
        self._home_scaffolder(profile)

    def migrate_home_contents(
        self,
        *,
        source_dir: str | None,
        target_home_dir: str,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        if self._home_migrator is None:
            return (), ()
        return self._home_migrator(source_dir, target_home_dir)

    def load_home_config(self, home_dir: str) -> dict[str, object]:
        if self._home_config_loader is None:
            raise AgentValidationError("Agent home config loading is unavailable.")
        return self._home_config_loader(f"{home_dir.rstrip('/')}/agent.json")

    def write_home_config(self, profile: AgentProfile, *, home_dir: str) -> Any:
        if self._home_config_writer is None:
            raise AgentValidationError("Agent home config writing is unavailable.")
        return self._home_config_writer(profile, home_dir)

    def apply_home_config(
        self,
        profile: AgentProfile,
        *,
        payload: dict[str, object],
        home_dir: str,
    ) -> AgentProfile:
        if self._home_config_applier is None:
            raise AgentValidationError("Agent home config syncing is unavailable.")
        return self._home_config_applier(profile, payload, home_dir)

    def read_home_files(self, home_dir: str) -> tuple[AgentHomeFileSnapshot, ...]:
        if self._home_file_reader is None:
            raise AgentValidationError("Agent home file reading is unavailable.")
        return tuple(
            AgentHomeFileSnapshot(
                name=item.name,
                path=item.path,
                exists=item.exists,
                language=item.language,
                content=item.content,
            )
            for item in self._home_file_reader(home_dir)
        )

    def write_home_files(
        self,
        home_dir: str,
        files: dict[str, str],
    ) -> tuple[AgentHomeFileSnapshot, ...]:
        if self._home_file_writer is None:
            raise AgentValidationError("Agent home file writing is unavailable.")
        try:
            written_files = self._home_file_writer(home_dir, files)
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
