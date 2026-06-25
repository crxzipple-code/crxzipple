from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from uuid import uuid4

from crxzipple.modules.skills.application.events import (
    SKILL_READINESS_CHANGED_EVENT,
    SKILL_RESOLUTION_COMPLETED_EVENT,
    SkillEventEmitter,
    emit_skill_event,
)
from crxzipple.modules.skills.application.environment import unsupported_platforms
from crxzipple.modules.skills.application.models import (
    SkillPackage,
    SkillReadiness,
    SkillReadinessStatus,
)
from crxzipple.modules.skills.application.owner_package_index import (
    DEFAULT_SOURCE_IDS,
    domain_source_type,
    package_id,
    package_index,
    package_root,
    source_policy_id,
    skill_policy_id,
)
from crxzipple.modules.skills.application.owner_readiness_projection import (
    catalog_readiness_changed_payload,
    prompt_readiness_snapshot,
    readiness_changed_payload,
    readiness_semantic,
    readiness_snapshot,
    removed_readiness_changed_payload,
)
from crxzipple.modules.skills.application.ports import (
    SkillOwnerCatalogRepositoryPort,
)
from crxzipple.modules.skills.application.runtime_request_resolver import (
    SkillRuntimeRequestResolution,
    SkillRuntimeRequestResolutionContext,
)
from crxzipple.modules.skills.domain import (
    SkillInstallation,
    SkillInstallationStatus,
    SkillPackageStatus,
    SkillReadinessSnapshot,
    SkillRuntimeVisibility,
    SkillSourceStatus,
    SkillSourceSyncStatus,
    SkillSource as DomainSkillSource,
    SkillReadinessStatus as DomainSkillReadinessStatus,
)


@dataclass(slots=True)
class SkillOwnerStateService:
    owner_catalog_repository: SkillOwnerCatalogRepositoryPort | None
    event_emitter: SkillEventEmitter | None = None

    def package_enabled(self, package: SkillPackage) -> bool:
        if self.owner_catalog_repository is None:
            return True
        source_policy = self.owner_catalog_repository.get_enablement_policy(
            source_policy_id(package.source),
        )
        if not _runtime_visible(source_policy):
            return False
        policy = self.owner_catalog_repository.get_enablement_policy(
            skill_policy_id(package.name),
        )
        return _runtime_visible(policy)

    def source_enabled(self, source_id: str) -> bool:
        if self.owner_catalog_repository is None:
            return True
        policy = self.owner_catalog_repository.get_enablement_policy(
            source_policy_id(source_id),
        )
        return _runtime_visible(policy)

    def domain_source(self, source_id: str) -> DomainSkillSource | None:
        if self.owner_catalog_repository is None:
            return None
        return self.owner_catalog_repository.get_source(source_id)

    def listed_persisted_sources(self) -> tuple[DomainSkillSource, ...]:
        if self.owner_catalog_repository is None:
            return ()
        return tuple(
            source
            for source in self.owner_catalog_repository.list_sources()
            if source.status is not SkillSourceStatus.DELETED
        )

    def record_installation(
        self,
        *,
        action: str,
        status: SkillInstallationStatus,
        package: SkillPackage | None = None,
        source_id: str | None = None,
        source_uri: str | None = None,
        target_uri: str | None = None,
        workspace_dir: str | None = None,
        reason: str | None = None,
        message: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        if self.owner_catalog_repository is None:
            return
        payload = dict(metadata or {})
        if workspace_dir:
            payload["workspace_dir"] = workspace_dir
        self.owner_catalog_repository.record_installation(
            SkillInstallation(
                installation_id=f"skill-installation:{uuid4().hex}",
                action=action,
                status=status,
                source_id=source_id or (package.source if package is not None else None),
                skill_id=package.name if package is not None else None,
                skill_name=package.name if package is not None else None,
                source_uri=source_uri,
                target_uri=target_uri,
                reason=reason,
                message=message,
                metadata=payload,
                created_at=utc_now(),
            ),
        )

    def persist_catalog_snapshot(
        self,
        *,
        packages: tuple[SkillPackage, ...],
        workspace_dir: str | None,
        source_id: str | None,
    ) -> None:
        if self.owner_catalog_repository is None:
            return
        now = utc_now()
        grouped: dict[str, list[SkillPackage]] = {}
        for package in packages:
            grouped.setdefault(package.source, []).append(package)
        for current_source_id, source_packages in grouped.items():
            roots = sorted({str(package_root(package)) for package in source_packages})
            existing_source = self.domain_source(current_source_id)
            if existing_source is not None and current_source_id not in DEFAULT_SOURCE_IDS:
                self.owner_catalog_repository.upsert_source(
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
                        last_synced_at=now,
                        updated_at=now,
                    ),
                )
                continue
            self.owner_catalog_repository.upsert_source(
                DomainSkillSource(
                    source_id=current_source_id,
                    source_type=domain_source_type(current_source_id),
                    root_uri=roots[0] if len(roots) == 1 else "",
                    status=SkillSourceStatus.ACTIVE,
                    sync_status=SkillSourceSyncStatus.SUCCEEDED,
                    scope=(
                        current_source_id
                        if current_source_id in DEFAULT_SOURCE_IDS
                        else None
                    ),
                    enabled=self.source_enabled(current_source_id),
                    readonly=current_source_id == "system",
                    metadata={
                        "root_paths": roots,
                        "workspace_dir": workspace_dir or "",
                    },
                    last_synced_at=now,
                    updated_at=now,
                ),
            )
        for package in packages:
            self.owner_catalog_repository.upsert_package(
                package_index(package, updated_at=now),
            )
        reconcile_sources = set(grouped)
        if source_id:
            reconcile_sources.add(source_id)
        for current_source_id in reconcile_sources:
            active_package_ids = {
                package_id(package)
                for package in grouped.get(current_source_id, ())
            }
            self._mark_missing_packages_removed(
                source_id=current_source_id,
                active_package_ids=active_package_ids,
                updated_at=now,
            )

    def persist_readiness_snapshots(
        self,
        *,
        packages: tuple[SkillPackage, ...],
        readiness: dict[str, SkillReadiness],
    ) -> None:
        if self.owner_catalog_repository is None:
            return
        now = utc_now()
        for package in packages:
            item = readiness.get(package.name)
            if item is None:
                continue
            previous = self.owner_catalog_repository.get_readiness(package.name)
            snapshot = readiness_snapshot(package, item, updated_at=now)
            self.owner_catalog_repository.upsert_readiness(snapshot)
            if readiness_semantic(previous) == readiness_semantic(snapshot):
                continue
            emit_skill_event(
                self.event_emitter,
                SKILL_READINESS_CHANGED_EVENT,
                payload=catalog_readiness_changed_payload(
                    package=package,
                    previous=previous,
                    current=snapshot,
                    readiness=item,
                ),
                status=snapshot.status.value,
                level=(
                    "info"
                    if snapshot.status is DomainSkillReadinessStatus.READY
                    else "warning"
                ),
            )

    def persist_runtime_request_readiness_snapshots(
        self,
        *,
        packages: tuple[SkillPackage, ...],
        resolution: SkillRuntimeRequestResolution,
        context: SkillRuntimeRequestResolutionContext,
    ) -> None:
        if self.owner_catalog_repository is None:
            return
        packages_by_name = {package.name: package for package in packages}
        now = utc_now()
        for resolved in resolution.skills:
            package = packages_by_name.get(resolved.package.name, resolved.package)
            snapshot = prompt_readiness_snapshot(
                package,
                resolved.readiness,
                context=context,
                updated_at=now,
            )
            previous = self.owner_catalog_repository.get_readiness(package.name)
            self.owner_catalog_repository.upsert_readiness(snapshot)
            if readiness_semantic(previous) == readiness_semantic(snapshot):
                continue
            emit_skill_event(
                self.event_emitter,
                SKILL_READINESS_CHANGED_EVENT,
                payload=readiness_changed_payload(
                    package=package,
                    previous=previous,
                    current=snapshot,
                    context=context,
                    readiness=resolved.readiness,
                ),
                status=snapshot.status.value,
                level=(
                    "info"
                    if snapshot.status is DomainSkillReadinessStatus.READY
                    else "warning"
                ),
            )

    def record_runtime_request_resolution_completed(
        self,
        *,
        resolution: SkillRuntimeRequestResolution,
        context: SkillRuntimeRequestResolutionContext,
    ) -> None:
        statuses = [resolved.readiness.status for resolved in resolution.skills]
        emit_skill_event(
            self.event_emitter,
            SKILL_RESOLUTION_COMPLETED_EVENT,
            payload={
                **context.attrs(),
                "total_count": len(resolution.skills),
                "ready_count": sum(1 for status in statuses if status == "ready"),
                "setup_needed_count": sum(
                    1 for status in statuses if status == "setup_needed"
                ),
                "unsupported_count": sum(
                    1 for status in statuses if status == "unsupported"
                ),
                "skills": [
                    {
                        "skill": resolved.package.name,
                        "status": resolved.readiness.status,
                        "missing_tools": list(resolved.readiness.missing_tools),
                        "missing_access": list(resolved.readiness.missing_access),
                        "missing_effects": list(resolved.readiness.missing_effects),
                        "unsupported_surfaces": list(
                            resolved.readiness.unsupported_surfaces,
                        ),
                        "unsupported_platforms": list(
                            resolved.readiness.unsupported_platforms,
                        ),
                    }
                    for resolved in resolution.skills
                ],
            },
            status="completed",
        )

    def readiness_for_package(self, package: SkillPackage) -> SkillReadiness:
        if not self.package_enabled(package):
            return SkillReadiness(
                status=SkillReadinessStatus.DISABLED,
                ready=False,
                setup_hints=package.requirements.setup_hints,
            )
        requirements = package.requirements
        missing_tools = requirements.required_tools
        missing_access = requirements.required_access
        missing_effects = requirements.required_effects
        unsupported_platform_values = unsupported_platforms(
            requirements.supported_platforms,
        )
        if unsupported_platform_values:
            return SkillReadiness(
                status=SkillReadinessStatus.UNSUPPORTED,
                ready=False,
                missing_tools=missing_tools,
                missing_access=missing_access,
                missing_effects=missing_effects,
                unsupported_platforms=unsupported_platform_values,
                setup_hints=requirements.setup_hints,
            )
        if missing_tools or missing_access or missing_effects:
            return SkillReadiness(
                status=SkillReadinessStatus.SETUP_NEEDED,
                ready=False,
                missing_tools=missing_tools,
                missing_access=missing_access,
                missing_effects=missing_effects,
                setup_hints=requirements.setup_hints,
            )
        return SkillReadiness(
            status=SkillReadinessStatus.READY,
            ready=True,
            setup_hints=requirements.setup_hints,
        )

    def _mark_missing_packages_removed(
        self,
        *,
        source_id: str,
        active_package_ids: set[str],
        updated_at: datetime,
    ) -> None:
        if self.owner_catalog_repository is None:
            return
        for package in self.owner_catalog_repository.list_packages(
            source_id=source_id,
            include_removed=True,
        ):
            if package.package_id in active_package_ids:
                continue
            if package.status is SkillPackageStatus.REMOVED:
                continue
            self.owner_catalog_repository.upsert_package(
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
            previous = self.owner_catalog_repository.get_readiness(package.skill_id)
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
            self.owner_catalog_repository.upsert_readiness(removed_snapshot)
            if readiness_semantic(previous) == readiness_semantic(removed_snapshot):
                continue
            emit_skill_event(
                self.event_emitter,
                SKILL_READINESS_CHANGED_EVENT,
                payload=removed_readiness_changed_payload(
                    package=package,
                    previous=previous,
                    current=removed_snapshot,
                ),
                status=removed_snapshot.status.value,
                level="warning",
            )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _runtime_visible(policy: object | None) -> bool:
    if policy is None:
        return True
    enabled = bool(getattr(policy, "enabled", False))
    visibility = getattr(policy, "runtime_visibility", SkillRuntimeVisibility.VISIBLE)
    return enabled and visibility is not SkillRuntimeVisibility.HIDDEN
