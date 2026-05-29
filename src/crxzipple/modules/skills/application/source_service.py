from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from crxzipple.modules.skills.application.catalog_service import SkillCatalogService
from crxzipple.modules.skills.application.events import (
    SKILL_SOURCE_CREATED_EVENT,
    SKILL_SOURCE_DELETED_EVENT,
    SKILL_SOURCE_SYNCED_EVENT,
    SKILL_SOURCE_UPDATED_EVENT,
    SkillEventEmitter,
    emit_skill_event,
)
from crxzipple.modules.skills.application.exceptions import (
    SkillCapabilityUnavailableError,
)
from crxzipple.modules.skills.application.models import (
    SkillPackage,
    SkillSource,
    SkillSourceCreateRequest,
    SkillSourceKind,
    SkillSourceMutationResult,
    SkillSourceUpdateRequest,
    SkillSyncResult,
)
from crxzipple.modules.skills.application.owner_state import (
    DEFAULT_SOURCE_IDS,
    SkillOwnerStateService,
    domain_source_type,
    utc_now,
)
from crxzipple.modules.skills.application.ports import (
    SkillOwnerCatalogRepositoryPort,
)
from crxzipple.modules.skills.domain import (
    SkillInstallationStatus,
    SkillNotFoundError,
    SkillSourceStatus,
    SkillSourceSyncStatus,
    SkillSourceType,
    SkillSource as DomainSkillSource,
    SkillValidationError,
)


@dataclass(slots=True)
class SkillSourceService:
    catalog_service: SkillCatalogService
    owner_state: SkillOwnerStateService
    owner_catalog_repository: SkillOwnerCatalogRepositoryPort | None = None
    event_emitter: SkillEventEmitter | None = None

    def list_sources(
        self,
        *,
        workspace_dir: str | None,
        surface: str,
    ) -> tuple[SkillSource, ...]:
        self.sync(workspace_dir=workspace_dir, source_id=None, surface=surface)
        packages = self.catalog_service.discover_packages(
            workspace_dir=workspace_dir,
            surface=surface,
        )
        grouped: dict[str, list[SkillPackage]] = {}
        for package in packages:
            grouped.setdefault(package.source, []).append(package)
        sources: list[SkillSource] = []
        for source_id, source_packages in sorted(grouped.items()):
            roots = sorted({str(Path(package.root_path).parent) for package in source_packages})
            domain_source = self.owner_state.domain_source(source_id)
            source_kind = _source_kind(
                domain_source.source_type.value if domain_source is not None else source_id,
            )
            readonly = (
                domain_source.readonly
                if domain_source is not None
                else source_kind is SkillSourceKind.SYSTEM
            )
            sources.append(
                SkillSource(
                    source_id=source_id,
                    source_kind=source_kind,
                    root_path=(
                        domain_source.root_uri
                        if domain_source is not None
                        else roots[0] if len(roots) == 1 else ""
                    ),
                    enabled=(
                        domain_source.enabled
                        if domain_source is not None
                        else self.owner_state.source_enabled(source_id)
                    ),
                    readonly=readonly,
                    package_count=len(source_packages),
                    metadata={
                        "root_paths": roots,
                        "workspace_dir": workspace_dir or "",
                    },
                    status=(
                        domain_source.status.value
                        if domain_source is not None
                        else SkillSourceStatus.ACTIVE.value
                    ),
                    sync_status=(
                        domain_source.sync_status.value
                        if domain_source is not None
                        else SkillSourceSyncStatus.SUCCEEDED.value
                    ),
                    priority=domain_source.priority if domain_source is not None else 100,
                ),
            )
        for source in self.owner_state.listed_persisted_sources():
            if source.source_id in grouped:
                continue
            sources.append(self.app_source_from_domain(source, package_count=0))
        return tuple(sources)

    def create_source(
        self,
        request: SkillSourceCreateRequest,
    ) -> SkillSourceMutationResult:
        repository = self._require_owner_catalog_repository("Skill source creation")
        now = utc_now()
        source_id = _normalize_source_id(request.source_id)
        self._ensure_custom_source_id(source_id)
        root_path = _normalize_source_root(request.root_path)
        source_type = domain_source_type(request.source_kind.value)
        if source_type not in {SkillSourceType.MANAGED, SkillSourceType.EXTERNAL}:
            raise SkillValidationError(
                "Custom skill sources must use managed or external source_kind.",
            )
        existing = repository.get_source(source_id)
        if existing is not None and existing.status is not SkillSourceStatus.DELETED:
            raise SkillValidationError(f"Skill source '{source_id}' already exists.")
        source = repository.upsert_source(
            DomainSkillSource(
                source_id=source_id,
                source_type=source_type,
                root_uri=root_path,
                status=SkillSourceStatus.ACTIVE,
                sync_status=SkillSourceSyncStatus.NEVER_SYNCED,
                scope=source_type.value,
                priority=request.priority,
                enabled=request.enabled,
                readonly=request.readonly,
                metadata=dict(request.metadata or {}),
                created_at=now,
                updated_at=now,
            ),
        )
        sync_result = self.sync(workspace_dir=None, source_id=source.source_id, surface="")
        source = repository.get_source(source.source_id) or source
        result = SkillSourceMutationResult(
            source=self.app_source_from_domain(
                source,
                package_count=sync_result.synced_count,
            ),
            action="create",
            changed=True,
            message=f"Skill source '{source.source_id}' created.",
        )
        self._emit_source_event(SKILL_SOURCE_CREATED_EVENT, result.source)
        self.owner_state.record_installation(
            action="source_create",
            status=SkillInstallationStatus.SUCCEEDED,
            source_id=result.source.source_id,
            target_uri=result.source.root_path,
            message=result.message,
            metadata={"source_kind": result.source.source_kind.value},
        )
        return result

    def update_source(
        self,
        request: SkillSourceUpdateRequest,
    ) -> SkillSourceMutationResult:
        repository = self._require_owner_catalog_repository("Skill source update")
        source_id = _normalize_source_id(request.source_id)
        source = repository.get_source(source_id)
        if source is None or source.status is SkillSourceStatus.DELETED:
            raise SkillNotFoundError(f"Skill source '{source_id}' is not available.")
        self._ensure_custom_source(source)
        updated = replace(
            source,
            root_uri=(
                _normalize_source_root(request.root_path)
                if request.root_path is not None
                else source.root_uri
            ),
            enabled=request.enabled if request.enabled is not None else source.enabled,
            readonly=request.readonly if request.readonly is not None else source.readonly,
            priority=request.priority if request.priority is not None else source.priority,
            metadata=(
                dict(request.metadata)
                if request.metadata is not None
                else dict(source.metadata)
            ),
            updated_at=utc_now(),
        )
        stored = repository.upsert_source(updated)
        sync_result = self.sync(workspace_dir=None, source_id=stored.source_id, surface="")
        stored = repository.get_source(stored.source_id) or stored
        result = SkillSourceMutationResult(
            source=self.app_source_from_domain(
                stored,
                package_count=sync_result.synced_count,
            ),
            action="update",
            changed=True,
            message=f"Skill source '{stored.source_id}' updated.",
        )
        self._emit_source_event(SKILL_SOURCE_UPDATED_EVENT, result.source)
        self.owner_state.record_installation(
            action="source_update",
            status=SkillInstallationStatus.SUCCEEDED,
            source_id=result.source.source_id,
            target_uri=result.source.root_path,
            message=result.message,
            metadata={"source_kind": result.source.source_kind.value},
        )
        return result

    def delete_source(
        self,
        *,
        source_id: str,
    ) -> SkillSourceMutationResult:
        repository = self._require_owner_catalog_repository("Skill source deletion")
        normalized_source_id = _normalize_source_id(source_id)
        source = repository.get_source(normalized_source_id)
        if source is None or source.status is SkillSourceStatus.DELETED:
            raise SkillNotFoundError(
                f"Skill source '{normalized_source_id}' is not available.",
            )
        self._ensure_custom_source(source)
        stored = repository.upsert_source(
            replace(
                source,
                status=SkillSourceStatus.DELETED,
                enabled=False,
                updated_at=utc_now(),
            ),
        )
        result = SkillSourceMutationResult(
            source=self.app_source_from_domain(stored, package_count=0),
            action="delete",
            changed=True,
            message=f"Skill source '{stored.source_id}' deleted.",
        )
        self._emit_source_event(SKILL_SOURCE_DELETED_EVENT, result.source)
        self.owner_state.record_installation(
            action="source_delete",
            status=SkillInstallationStatus.SUCCEEDED,
            source_id=result.source.source_id,
            target_uri=result.source.root_path,
            message=result.message,
            metadata={"source_kind": result.source.source_kind.value},
        )
        return result

    def sync(
        self,
        *,
        workspace_dir: str | None,
        source_id: str | None,
        surface: str,
    ) -> SkillSyncResult:
        result = self._sync_snapshot(
            workspace_dir=workspace_dir,
            source_id=source_id,
            surface=surface,
        )
        emit_skill_event(
            self.event_emitter,
            SKILL_SOURCE_SYNCED_EVENT,
            status="succeeded",
            payload={
                "source": result.source_id or "",
                "source_id": result.source_id or "",
                "workspace_dir": workspace_dir or "",
                "surface": surface,
                "synced_count": result.synced_count,
                "skills": [package.name for package in result.packages],
            },
        )
        self.owner_state.record_installation(
            action="source_sync",
            status=SkillInstallationStatus.SUCCEEDED,
            source_id=result.source_id,
            workspace_dir=workspace_dir,
            message="Skill source synchronized.",
            metadata={
                "surface": surface,
                "synced_count": result.synced_count,
                "skills": [package.name for package in result.packages],
            },
        )
        return result

    def app_source_from_domain(
        self,
        source: DomainSkillSource,
        *,
        package_count: int,
    ) -> SkillSource:
        return SkillSource(
            source_id=source.source_id,
            source_kind=_source_kind(source.source_type.value),
            root_path=source.root_uri,
            enabled=source.enabled,
            readonly=source.readonly,
            package_count=package_count,
            metadata=dict(source.metadata),
            status=source.status.value,
            sync_status=source.sync_status.value,
            priority=source.priority,
        )

    def _sync_snapshot(
        self,
        *,
        workspace_dir: str | None,
        source_id: str | None,
        surface: str,
    ) -> SkillSyncResult:
        packages = self.catalog_service.discover_packages(
            workspace_dir=workspace_dir,
            surface=surface,
        )
        normalized_source = source_id.strip() if source_id else None
        if normalized_source:
            packages = tuple(
                package for package in packages if package.source == normalized_source
            )
        self.owner_state.persist_catalog_snapshot(
            packages=packages,
            workspace_dir=workspace_dir,
            source_id=normalized_source,
        )
        return SkillSyncResult(
            source_id=normalized_source,
            synced_count=len(packages),
            packages=packages,
        )

    def _require_owner_catalog_repository(
        self,
        capability: str,
    ) -> SkillOwnerCatalogRepositoryPort:
        if self.owner_catalog_repository is None:
            raise SkillCapabilityUnavailableError(
                f"{capability} requires a skill owner catalog repository.",
            )
        return self.owner_catalog_repository

    def _ensure_custom_source_id(self, source_id: str) -> None:
        if source_id in DEFAULT_SOURCE_IDS:
            raise SkillValidationError(
                f"Skill source '{source_id}' is managed by the runtime and cannot be edited.",
            )

    def _ensure_custom_source(self, source: DomainSkillSource) -> None:
        self._ensure_custom_source_id(source.source_id)
        if source.source_type not in (SkillSourceType.MANAGED, SkillSourceType.EXTERNAL):
            raise SkillValidationError(
                f"Skill source '{source.source_id}' is not a custom editable source.",
            )

    def _emit_source_event(
        self,
        event_name: str,
        source: SkillSource,
    ) -> None:
        emit_skill_event(
            self.event_emitter,
            event_name,
            status="succeeded",
            payload={
                "source": source.source_id,
                "source_id": source.source_id,
                "source_kind": source.source_kind.value,
                "root_path": source.root_path,
                "enabled": source.enabled,
                "readonly": source.readonly,
                "package_count": source.package_count,
                "status": source.status,
                "sync_status": source.sync_status,
            },
        )


def _source_kind(source_id: str) -> SkillSourceKind:
    try:
        return SkillSourceKind(source_id)
    except ValueError:
        return SkillSourceKind.UNKNOWN


def _normalize_source_id(source_id: str) -> str:
    normalized = source_id.strip()
    if not normalized:
        raise SkillValidationError("Skill source id is required.")
    if "/" in normalized or "\\" in normalized:
        raise SkillValidationError("Skill source id cannot contain path separators.")
    return normalized


def _normalize_source_root(root_path: str) -> str:
    candidate = root_path.strip()
    if not candidate:
        raise SkillValidationError("Skill source root_path is required.")
    try:
        resolved = Path(candidate).expanduser().resolve(strict=True)
    except OSError as exc:
        raise SkillValidationError(
            f"Skill source root_path '{candidate}' could not be resolved.",
        ) from exc
    if not resolved.is_dir():
        raise SkillValidationError(
            f"Skill source root_path '{candidate}' is not a directory.",
        )
    return str(resolved)
