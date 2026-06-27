from __future__ import annotations

from dataclasses import dataclass, replace

from crxzipple.modules.skills.application.catalog_service import SkillCatalogService
from crxzipple.modules.skills.application.events import (
    SKILL_SOURCE_CREATED_EVENT,
    SKILL_SOURCE_DELETED_EVENT,
    SKILL_SOURCE_UPDATED_EVENT,
    SkillEventEmitter,
)
from crxzipple.modules.skills.application.exceptions import (
    SkillCapabilityUnavailableError,
)
from crxzipple.modules.skills.application.models import (
    SkillSource,
    SkillSourceCreateRequest,
    SkillSourceMutationResult,
    SkillSourceUpdateRequest,
    SkillSyncResult,
)
from crxzipple.modules.skills.application.owner_state import (
    SkillOwnerStateService,
    utc_now,
)
from crxzipple.modules.skills.application.ports import (
    SkillOwnerCatalogRepositoryPort,
)
from crxzipple.modules.skills.application.source_observation import (
    emit_source_event,
    emit_source_synced,
    record_source_mutation,
    record_source_sync,
)
from crxzipple.modules.skills.application.source_projection import (
    app_source_from_domain,
    build_app_sources,
)
from crxzipple.modules.skills.application.source_validation import (
    editable_source_type,
    ensure_custom_source,
    ensure_custom_source_id,
    normalize_source_id,
    normalize_source_root,
)
from crxzipple.modules.skills.domain import (
    SkillNotFoundError,
    SkillValidationError,
    SkillSourceStatus,
    SkillSourceSyncStatus,
    SkillSource as DomainSkillSource,
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
        return build_app_sources(
            owner_state=self.owner_state,
            packages=packages,
            workspace_dir=workspace_dir,
        )

    def create_source(
        self,
        request: SkillSourceCreateRequest,
    ) -> SkillSourceMutationResult:
        repository = self._require_owner_catalog_repository("Skill source creation")
        now = utc_now()
        source_id = normalize_source_id(request.source_id)
        ensure_custom_source_id(source_id)
        root_path = normalize_source_root(request.root_path)
        source_type = editable_source_type(request.source_kind.value)
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
            source=app_source_from_domain(
                source,
                package_count=sync_result.synced_count,
            ),
            action="create",
            changed=True,
            message=f"Skill source '{source.source_id}' created.",
        )
        emit_source_event(self.event_emitter, SKILL_SOURCE_CREATED_EVENT, result.source)
        record_source_mutation(
            self.owner_state,
            action="source_create",
            source=result.source,
            message=result.message,
        )
        return result

    def update_source(
        self,
        request: SkillSourceUpdateRequest,
    ) -> SkillSourceMutationResult:
        repository = self._require_owner_catalog_repository("Skill source update")
        source_id = normalize_source_id(request.source_id)
        source = repository.get_source(source_id)
        if source is None or source.status is SkillSourceStatus.DELETED:
            raise SkillNotFoundError(f"Skill source '{source_id}' is not available.")
        ensure_custom_source(source)
        updated = replace(
            source,
            root_uri=(
                normalize_source_root(request.root_path)
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
            source=app_source_from_domain(
                stored,
                package_count=sync_result.synced_count,
            ),
            action="update",
            changed=True,
            message=f"Skill source '{stored.source_id}' updated.",
        )
        emit_source_event(self.event_emitter, SKILL_SOURCE_UPDATED_EVENT, result.source)
        record_source_mutation(
            self.owner_state,
            action="source_update",
            source=result.source,
            message=result.message,
        )
        return result

    def delete_source(
        self,
        *,
        source_id: str,
    ) -> SkillSourceMutationResult:
        repository = self._require_owner_catalog_repository("Skill source deletion")
        normalized_source_id = normalize_source_id(source_id)
        source = repository.get_source(normalized_source_id)
        if source is None or source.status is SkillSourceStatus.DELETED:
            raise SkillNotFoundError(
                f"Skill source '{normalized_source_id}' is not available.",
            )
        ensure_custom_source(source)
        stored = repository.upsert_source(
            replace(
                source,
                status=SkillSourceStatus.DELETED,
                enabled=False,
                updated_at=utc_now(),
            ),
        )
        result = SkillSourceMutationResult(
            source=app_source_from_domain(stored, package_count=0),
            action="delete",
            changed=True,
            message=f"Skill source '{stored.source_id}' deleted.",
        )
        emit_source_event(self.event_emitter, SKILL_SOURCE_DELETED_EVENT, result.source)
        record_source_mutation(
            self.owner_state,
            action="source_delete",
            source=result.source,
            message=result.message,
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
        emit_source_synced(
            self.event_emitter,
            result,
            workspace_dir=workspace_dir,
            surface=surface,
        )
        record_source_sync(
            self.owner_state,
            result,
            workspace_dir=workspace_dir,
            surface=surface,
        )
        return result

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
