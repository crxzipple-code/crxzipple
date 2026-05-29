from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
from typing import Protocol

from crxzipple.app.integration.memory_scope_resolution import memory_scope_owner_kind
from crxzipple.modules.agent.application import UpdateAgentProfileInput
from crxzipple.modules.agent.domain import AgentMemoryBinding, AgentProfile
from crxzipple.modules.memory.application import MemorySpaceService


@dataclass(frozen=True, slots=True)
class LegacyMemoryAgentMigrationReport:
    agent_id: str
    home_dir: str | None
    scope_ref: str
    sidecar_path: str | None = None
    sidecar_imported: bool = False
    sidecar_deleted: bool = False
    profile_updated: bool = False
    space_created: bool = False
    copied_paths: tuple[str, ...] = ()
    skipped_paths: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LegacyMemoryMigrationReport:
    dry_run: bool
    agents: tuple[LegacyMemoryAgentMigrationReport, ...]

    @property
    def scanned(self) -> int:
        return len(self.agents)

    @property
    def updated_profiles(self) -> int:
        return sum(1 for item in self.agents if item.profile_updated)

    @property
    def created_spaces(self) -> int:
        return sum(1 for item in self.agents if item.space_created)

    @property
    def copied_files(self) -> int:
        return sum(len(item.copied_paths) for item in self.agents)


class _AgentProfileService(Protocol):
    def list_profiles(self) -> list[AgentProfile]:
        ...

    def update_profile(self, data: UpdateAgentProfileInput) -> AgentProfile:
        ...


class MemoryLegacyMigrationService:
    def __init__(
        self,
        *,
        agent_service: _AgentProfileService,
        memory_spaces: MemorySpaceService,
        default_retrieval_backend: str,
    ) -> None:
        self._agent_service = agent_service
        self._memory_spaces = memory_spaces
        self._default_retrieval_backend = default_retrieval_backend

    def migrate_agent_homes(
        self,
        *,
        agent_ids: tuple[str, ...] = (),
        dry_run: bool = False,
        delete_sidecar: bool = False,
    ) -> LegacyMemoryMigrationReport:
        selected_ids = {item.strip() for item in agent_ids if item.strip()}
        reports: list[LegacyMemoryAgentMigrationReport] = []
        for profile in self._agent_service.list_profiles():
            if selected_ids and profile.id not in selected_ids:
                continue
            reports.append(
                self._migrate_profile(
                    profile,
                    dry_run=dry_run,
                    delete_sidecar=delete_sidecar,
                ),
            )
        return LegacyMemoryMigrationReport(dry_run=dry_run, agents=tuple(reports))

    def _migrate_profile(
        self,
        profile: AgentProfile,
        *,
        dry_run: bool,
        delete_sidecar: bool,
    ) -> LegacyMemoryAgentMigrationReport:
        home_dir = profile.runtime_preferences.resolved_home_dir
        home_root = Path(home_dir).expanduser() if home_dir else None
        sidecar = home_root / ".state" / "memory-binding.json" if home_root else None
        sidecar_was_file = sidecar is not None and sidecar.is_file()
        sidecar_payload, sidecar_error = _load_sidecar(sidecar)
        target_memory = _memory_binding_from_sidecar(profile, sidecar_payload)
        scope_ref = target_memory.effective_scope_ref(profile.id)
        existing_space = self._memory_spaces.get_space(scope_ref)
        storage_root = self._memory_spaces.storage_root_for_scope(scope_ref)
        copied_paths, skipped_paths, copy_errors = _copy_legacy_memory_files(
            source_root=home_root,
            target_root=Path(storage_root).expanduser(),
            dry_run=dry_run,
        )
        profile_updated = target_memory != profile.memory
        sidecar_imported = sidecar_payload is not None
        sidecar_deleted = False

        if not dry_run:
            if profile_updated:
                self._agent_service.update_profile(
                    UpdateAgentProfileInput(
                        id=profile.id,
                        memory=target_memory,
                        reason="memory_legacy_agent_home_migration",
                    ),
                )
            self._memory_spaces.ensure_space(
                scope_ref=scope_ref,
                owner_kind=memory_scope_owner_kind(scope_ref, agent_id=profile.id),
                owner_id=profile.id,
                retrieval_backend=self._default_retrieval_backend,
            )
            if delete_sidecar and sidecar is not None and sidecar.is_file():
                sidecar.unlink()
                sidecar_deleted = True

        errors = tuple(item for item in (sidecar_error, *copy_errors) if item)
        return LegacyMemoryAgentMigrationReport(
            agent_id=profile.id,
            home_dir=str(home_root) if home_root is not None else None,
            scope_ref=scope_ref,
            sidecar_path=str(sidecar) if sidecar_was_file else None,
            sidecar_imported=sidecar_imported,
            sidecar_deleted=sidecar_deleted,
            profile_updated=profile_updated,
            space_created=existing_space is None,
            copied_paths=tuple(copied_paths),
            skipped_paths=tuple(skipped_paths),
            errors=errors,
        )


def _load_sidecar(path: Path | None) -> tuple[dict[str, object] | None, str | None]:
    if path is None or not path.is_file():
        return None, None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, f"{path}: invalid JSON ({exc.msg})"
    if not isinstance(payload, dict):
        return None, f"{path}: expected JSON object"
    return payload, None


def _memory_binding_from_sidecar(
    profile: AgentProfile,
    payload: dict[str, object] | None,
) -> AgentMemoryBinding:
    if payload is None:
        return profile.memory
    memory_payload = payload.get("memory")
    if isinstance(memory_payload, dict):
        payload = memory_payload
    scope_ref = _first_text(
        payload,
        "scope_ref",
        "memory_scope_ref",
        "memory_space_id",
        "memory_space",
        "space_id",
    )
    enabled = payload.get("enabled")
    access = _first_text(payload, "access") or profile.memory.access
    return AgentMemoryBinding(
        enabled=bool(enabled) if enabled is not None else profile.memory.enabled,
        scope_ref=scope_ref or profile.memory.scope_ref,
        access=access,
    )


def _first_text(payload: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _copy_legacy_memory_files(
    *,
    source_root: Path | None,
    target_root: Path,
    dry_run: bool,
) -> tuple[list[str], list[str], list[str]]:
    copied: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []
    if source_root is None or not source_root.exists():
        return copied, skipped, errors

    for source_name in ("MEMORY.md", "memory.md"):
        source_path = source_root / source_name
        if not source_path.is_file():
            continue
        target_path = target_root / "MEMORY.md"
        _copy_file(
            source_path=source_path,
            target_path=target_path,
            label=f"{source_name} -> MEMORY.md",
            dry_run=dry_run,
            copied=copied,
            skipped=skipped,
            errors=errors,
        )

    memory_dir = source_root / "memory"
    if memory_dir.is_dir():
        for source_path in sorted(memory_dir.rglob("*")):
            if not source_path.is_file():
                continue
            relative = source_path.relative_to(memory_dir)
            target_path = target_root / "memory" / relative
            _copy_file(
                source_path=source_path,
                target_path=target_path,
                label=f"memory/{relative.as_posix()}",
                dry_run=dry_run,
                copied=copied,
                skipped=skipped,
                errors=errors,
            )
    return copied, skipped, errors


def _copy_file(
    *,
    source_path: Path,
    target_path: Path,
    label: str,
    dry_run: bool,
    copied: list[str],
    skipped: list[str],
    errors: list[str],
) -> None:
    if target_path.exists():
        skipped.append(label)
        return
    copied.append(label)
    if dry_run:
        return
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
    except OSError as exc:
        copied.pop()
        errors.append(f"{source_path}: {exc}")
