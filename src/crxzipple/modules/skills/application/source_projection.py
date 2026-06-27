from __future__ import annotations

from pathlib import Path

from crxzipple.modules.skills.application.models import (
    SkillPackage,
    SkillSource,
    SkillSourceKind,
)
from crxzipple.modules.skills.application.owner_state import SkillOwnerStateService
from crxzipple.modules.skills.domain import (
    SkillSource as DomainSkillSource,
    SkillSourceStatus,
    SkillSourceSyncStatus,
)


def build_app_sources(
    *,
    owner_state: SkillOwnerStateService,
    packages: tuple[SkillPackage, ...],
    workspace_dir: str | None,
) -> tuple[SkillSource, ...]:
    grouped: dict[str, list[SkillPackage]] = {}
    for package in packages:
        grouped.setdefault(package.source, []).append(package)

    sources: list[SkillSource] = []
    for source_id, source_packages in sorted(grouped.items()):
        sources.append(
            app_source_from_packages(
                owner_state=owner_state,
                source_id=source_id,
                packages=tuple(source_packages),
                workspace_dir=workspace_dir,
            ),
        )
    for source in owner_state.listed_persisted_sources():
        if source.source_id in grouped:
            continue
        sources.append(app_source_from_domain(source, package_count=0))
    return tuple(sources)


def app_source_from_packages(
    *,
    owner_state: SkillOwnerStateService,
    source_id: str,
    packages: tuple[SkillPackage, ...],
    workspace_dir: str | None,
) -> SkillSource:
    roots = sorted({str(Path(package.root_path).parent) for package in packages})
    domain_source = owner_state.domain_source(source_id)
    source_kind = source_kind_from_id(
        domain_source.source_type.value if domain_source is not None else source_id,
    )
    readonly = (
        domain_source.readonly
        if domain_source is not None
        else source_kind is SkillSourceKind.SYSTEM
    )
    return SkillSource(
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
            else owner_state.source_enabled(source_id)
        ),
        readonly=readonly,
        package_count=len(packages),
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
    )


def app_source_from_domain(
    source: DomainSkillSource,
    *,
    package_count: int,
) -> SkillSource:
    return SkillSource(
        source_id=source.source_id,
        source_kind=source_kind_from_id(source.source_type.value),
        root_path=source.root_uri,
        enabled=source.enabled,
        readonly=source.readonly,
        package_count=package_count,
        metadata=dict(source.metadata),
        status=source.status.value,
        sync_status=source.sync_status.value,
        priority=source.priority,
    )


def source_kind_from_id(source_id: str) -> SkillSourceKind:
    try:
        return SkillSourceKind(source_id)
    except ValueError:
        return SkillSourceKind.UNKNOWN
