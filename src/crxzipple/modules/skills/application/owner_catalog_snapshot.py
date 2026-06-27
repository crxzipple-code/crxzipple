from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from crxzipple.modules.skills.application.events import (
    SKILL_READINESS_CHANGED_EVENT,
    SkillEventEmitter,
    emit_skill_event,
)
from crxzipple.modules.skills.application.models import SkillPackage
from crxzipple.modules.skills.application.owner_package_index import (
    DEFAULT_SOURCE_IDS,
    domain_source_type,
    package_id,
    package_index,
    package_root,
)
from crxzipple.modules.skills.application.owner_readiness_projection import (
    readiness_semantic,
    removed_readiness_changed_payload,
)
from crxzipple.modules.skills.application.ports import SkillOwnerCatalogRepositoryPort
from crxzipple.modules.skills.domain import (
    SkillPackageStatus,
    SkillReadinessSnapshot,
    SkillReadinessStatus as DomainSkillReadinessStatus,
    SkillSource as DomainSkillSource,
    SkillSourceStatus,
    SkillSourceSyncStatus,
)


def persist_catalog_snapshot(
    *,
    repository: SkillOwnerCatalogRepositoryPort,
    event_emitter: SkillEventEmitter | None,
    packages: tuple[SkillPackage, ...],
    workspace_dir: str | None,
    source_id: str | None,
    source_enabled: Callable[[str], bool],
    updated_at: datetime,
) -> None:
    grouped = packages_by_source(packages)
    for current_source_id, source_packages in grouped.items():
        upsert_source_snapshot(
            repository=repository,
            source_id=current_source_id,
            packages=tuple(source_packages),
            workspace_dir=workspace_dir,
            source_enabled=source_enabled,
            updated_at=updated_at,
        )
    for package in packages:
        repository.upsert_package(package_index(package, updated_at=updated_at))
    reconcile_sources = set(grouped)
    if source_id:
        reconcile_sources.add(source_id)
    for current_source_id in reconcile_sources:
        active_package_ids = {
            package_id(package)
            for package in grouped.get(current_source_id, ())
        }
        mark_missing_packages_removed(
            repository=repository,
            event_emitter=event_emitter,
            source_id=current_source_id,
            active_package_ids=active_package_ids,
            updated_at=updated_at,
        )


def packages_by_source(
    packages: tuple[SkillPackage, ...],
) -> dict[str, list[SkillPackage]]:
    grouped: dict[str, list[SkillPackage]] = {}
    for package in packages:
        grouped.setdefault(package.source, []).append(package)
    return grouped


def upsert_source_snapshot(
    *,
    repository: SkillOwnerCatalogRepositoryPort,
    source_id: str,
    packages: tuple[SkillPackage, ...],
    workspace_dir: str | None,
    source_enabled: Callable[[str], bool],
    updated_at: datetime,
) -> None:
    roots = sorted({str(package_root(package)) for package in packages})
    existing_source = repository.get_source(source_id)
    if existing_source is not None and source_id not in DEFAULT_SOURCE_IDS:
        repository.upsert_source(
            replace(
                existing_source,
                root_uri=existing_source.root_uri,
                status=SkillSourceStatus.ACTIVE,
                sync_status=SkillSourceSyncStatus.SUCCEEDED,
                metadata={
                    **dict(existing_source.metadata),
                    "root_paths": roots,
                    "workspace_dir": workspace_dir or "",
                },
                last_synced_at=updated_at,
                updated_at=updated_at,
            ),
        )
        return
    repository.upsert_source(
        DomainSkillSource(
            source_id=source_id,
            source_type=domain_source_type(source_id),
            root_uri=roots[0] if len(roots) == 1 else "",
            status=SkillSourceStatus.ACTIVE,
            sync_status=SkillSourceSyncStatus.SUCCEEDED,
            scope=source_id if source_id in DEFAULT_SOURCE_IDS else None,
            enabled=source_enabled(source_id),
            readonly=source_id == "system",
            metadata={
                "root_paths": roots,
                "workspace_dir": workspace_dir or "",
            },
            last_synced_at=updated_at,
            updated_at=updated_at,
        ),
    )


def mark_missing_packages_removed(
    *,
    repository: SkillOwnerCatalogRepositoryPort,
    event_emitter: SkillEventEmitter | None,
    source_id: str,
    active_package_ids: set[str],
    updated_at: datetime,
) -> None:
    for package in repository.list_packages(
        source_id=source_id,
        include_removed=True,
    ):
        if package.package_id in active_package_ids:
            continue
        if package.status is SkillPackageStatus.REMOVED:
            continue
        repository.upsert_package(
            replace(
                package,
                status=SkillPackageStatus.REMOVED,
                metadata={
                    **dict(package.metadata),
                    "removed_at": updated_at.isoformat(),
                },
                updated_at=updated_at,
            ),
        )
        previous = repository.get_readiness(package.skill_id)
        removed_snapshot = SkillReadinessSnapshot(
            skill_id=package.skill_id,
            status=DomainSkillReadinessStatus.INVALID,
            source_id=source_id,
            reason="removed",
            checks=(
                {
                    "kind": "package",
                    "id": "skill_package_removed",
                    "ok": False,
                    "message": "Skill package is no longer present in its source.",
                },
            ),
            metadata={"package_id": package.package_id},
            updated_at=updated_at,
        )
        repository.upsert_readiness(removed_snapshot)
        if readiness_semantic(previous) == readiness_semantic(removed_snapshot):
            continue
        emit_skill_event(
            event_emitter,
            SKILL_READINESS_CHANGED_EVENT,
            payload=removed_readiness_changed_payload(
                package=package,
                previous=previous,
                current=removed_snapshot,
            ),
            status=removed_snapshot.status.value,
            level="warning",
        )
