from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
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
from crxzipple.modules.skills.application.ports import (
    SkillOwnerCatalogRepositoryPort,
)
from crxzipple.modules.skills.application.runtime_request_resolver import (
    ResolvedSkillReadiness,
    SkillRuntimeRequestResolution,
    SkillRuntimeRequestResolutionContext,
)
from crxzipple.modules.skills.domain import (
    SkillInstallation,
    SkillInstallationStatus,
    SkillPackageIndex,
    SkillPackageStatus,
    SkillReadinessSnapshot,
    SkillSourceStatus,
    SkillSourceSyncStatus,
    SkillSourceType,
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
        policy = self.owner_catalog_repository.get_enablement_policy(
            skill_policy_id(package.name),
        )
        return True if policy is None else policy.enabled

    def source_enabled(self, source_id: str) -> bool:
        if self.owner_catalog_repository is None:
            return True
        policy = self.owner_catalog_repository.get_enablement_policy(
            f"source:{source_id}:enablement",
        )
        return True if policy is None else policy.enabled

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
            roots = sorted({str(_package_root(package)) for package in source_packages})
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


DEFAULT_SOURCE_IDS = frozenset({"workspace", "global", "system"})


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def skill_policy_id(skill_name: str) -> str:
    return f"skill:{skill_name}:enablement"


def domain_source_type(source_id: str) -> SkillSourceType:
    try:
        return SkillSourceType(source_id)
    except ValueError:
        return SkillSourceType.EXTERNAL


def package_id(package: SkillPackage) -> str:
    return f"{package.source}:{package.name}"


def package_index(package: SkillPackage, *, updated_at: datetime) -> SkillPackageIndex:
    return SkillPackageIndex(
        package_id=package_id(package),
        skill_id=package.name,
        name=package.name,
        source_id=package.source,
        root_uri=package.root_path,
        manifest_uri=package.manifest_path,
        instructions_uri=package.instructions_path,
        version=package.version,
        fingerprint=package.fingerprint or package_fingerprint(package),
        status=SkillPackageStatus.ACTIVE,
        requirements=package.requirements,
        capability_requirements={
            "required_tools": list(package.requirements.required_tools),
            "required_effects": list(package.requirements.required_effects),
            "required_access": list(package.requirements.required_access),
            "supported_platforms": list(package.requirements.supported_platforms),
        },
        metadata={
            "tags": list(package.tags),
            "description": package.description,
            "source": package.source,
        },
        indexed_at=updated_at,
        updated_at=updated_at,
    )


def package_fingerprint(package: SkillPackage) -> str:
    fingerprint_input = "|".join(
        (
            package.name,
            package.version or "",
            package.source,
            package.root_path,
            package.manifest_path,
            package.instructions_path,
        ),
    )
    return f"sha256:{hashlib.sha256(fingerprint_input.encode('utf-8')).hexdigest()}"


def readiness_snapshot(
    package: SkillPackage,
    readiness: SkillReadiness,
    *,
    updated_at: datetime,
) -> SkillReadinessSnapshot:
    checks: list[dict[str, object]] = []
    checks.extend(
        {"kind": "tool", "id": item, "ok": False}
        for item in readiness.missing_tools
    )
    checks.extend(
        {"kind": "access", "id": item, "ok": False}
        for item in readiness.missing_access
    )
    checks.extend(
        {"kind": "authorization_effect", "id": item, "ok": False}
        for item in readiness.missing_effects
    )
    checks.extend(
        {"kind": "surface", "id": item, "ok": False, "status": "unsupported"}
        for item in readiness.unsupported_surfaces
    )
    checks.extend(
        {"kind": "platform", "id": item, "ok": False, "status": "unsupported"}
        for item in readiness.unsupported_platforms
    )
    if not checks and readiness.ready:
        checks.append({"kind": "manifest", "id": package.name, "ok": True})
    return SkillReadinessSnapshot(
        skill_id=package.name,
        source_id=package.source,
        status=domain_readiness_status(readiness.status),
        checks=tuple(checks),
        reason=None if readiness.ready else readiness.status.value,
        metadata={
            "setup_hints": list(readiness.setup_hints),
            "validation_errors": list(readiness.validation_errors),
            "missing_effects": list(readiness.missing_effects),
            "unsupported_surfaces": list(readiness.unsupported_surfaces),
            "unsupported_platforms": list(readiness.unsupported_platforms),
        },
        updated_at=updated_at,
    )


def domain_readiness_status(
    status: SkillReadinessStatus,
) -> DomainSkillReadinessStatus:
    try:
        return DomainSkillReadinessStatus(status.value)
    except ValueError:
        return DomainSkillReadinessStatus.UNSUPPORTED


def prompt_readiness_snapshot(
    package: SkillPackage,
    readiness: ResolvedSkillReadiness,
    *,
    context: SkillRuntimeRequestResolutionContext,
    updated_at: datetime,
) -> SkillReadinessSnapshot:
    checks = prompt_readiness_checks(package, readiness)
    if not checks and readiness.ready:
        checks = ({"kind": "manifest", "id": package.name, "ok": True},)
    return SkillReadinessSnapshot(
        skill_id=package.name,
        source_id=package.source,
        status=_prompt_snapshot_status(readiness),
        checks=checks,
        reason=None if readiness.ready else readiness.status,
        metadata={
            "source": package.source,
            "surface": context.surface or "",
            "agent_id": context.agent_id or "",
            "setup_hints": list(package.requirements.setup_hints),
            "access_checks": [
                check.to_metadata()
                for check in readiness.access_checks
            ],
            "authorization": (
                readiness.authorization.to_metadata()
                if readiness.authorization is not None
                else None
            ),
        },
        updated_at=updated_at,
    )


def prompt_readiness_checks(
    package: SkillPackage,
    readiness: ResolvedSkillReadiness,
) -> tuple[dict[str, object], ...]:
    checks: list[dict[str, object]] = []
    missing_tools = set(readiness.missing_tools)
    for tool_id in package.requirements.required_tools:
        checks.append(
            {
                "kind": "tool",
                "id": tool_id,
                "ok": tool_id not in missing_tools,
            },
        )
    for check in readiness.access_checks:
        payload = check.to_metadata()
        checks.append(
            {
                "kind": "access",
                "id": check.requirement,
                "ok": check.ready,
                "status": check.status,
                "setup_available": check.setup_available,
                "reason": payload.get("reason", ""),
            },
        )
    checked_access = {check.requirement for check in readiness.access_checks}
    for requirement in readiness.missing_access:
        if requirement in checked_access:
            continue
        checks.append(
            {
                "kind": "access",
                "id": requirement,
                "ok": False,
                "status": "setup_needed",
            },
        )
    missing_effects = set(readiness.missing_effects)
    for effect_id in package.requirements.required_effects:
        checks.append(
            {
                "kind": "authorization_effect",
                "id": effect_id,
                "ok": effect_id not in missing_effects,
            },
        )
    for surface in readiness.unsupported_surfaces:
        checks.append(
            {
                "kind": "surface",
                "id": surface,
                "ok": False,
                "status": "unsupported",
            },
        )
    for platform in readiness.unsupported_platforms:
        checks.append(
            {
                "kind": "platform",
                "id": platform,
                "ok": False,
                "status": "unsupported",
            },
        )
    return tuple(checks)


def readiness_semantic(
    snapshot: SkillReadinessSnapshot | None,
) -> tuple[object, ...] | None:
    if snapshot is None:
        return None
    return (
        snapshot.status.value,
        snapshot.reason,
        tuple(normalized_check(check) for check in snapshot.checks),
    )


def normalized_check(check: dict[str, object]) -> tuple[tuple[str, object], ...]:
    return tuple(sorted(check.items(), key=lambda item: item[0]))


def readiness_changed_payload(
    *,
    package: SkillPackage,
    previous: SkillReadinessSnapshot | None,
    current: SkillReadinessSnapshot,
    context: SkillRuntimeRequestResolutionContext,
    readiness: ResolvedSkillReadiness,
) -> dict[str, object]:
    return {
        "skill": package.name,
        "skill_name": package.name,
        "source": package.source,
        "previous_status": previous.status.value if previous is not None else "",
        "status": current.status.value,
        "ready": current.status is DomainSkillReadinessStatus.READY,
        "run_id": context.run_id or "",
        "agent_id": context.agent_id or "",
        "session_key": context.session_key or "",
        "active_session_id": context.active_session_id or "",
        "surface": context.surface or "",
        "workspace_dir": context.workspace_dir or "",
        "missing_tools": list(readiness.missing_tools),
        "missing_access": list(readiness.missing_access),
        "missing_effects": list(readiness.missing_effects),
        "unsupported_surfaces": list(readiness.unsupported_surfaces),
        "unsupported_platforms": list(readiness.unsupported_platforms),
        "checks": [dict(check) for check in current.checks],
    }


def catalog_readiness_changed_payload(
    *,
    package: SkillPackage,
    previous: SkillReadinessSnapshot | None,
    current: SkillReadinessSnapshot,
    readiness: SkillReadiness,
) -> dict[str, object]:
    return {
        "skill": package.name,
        "skill_name": package.name,
        "source": package.source,
        "path": package.root_path,
        "previous_status": previous.status.value if previous is not None else "",
        "status": current.status.value,
        "ready": current.status is DomainSkillReadinessStatus.READY,
        "readiness_scope": "catalog",
        "missing_tools": list(readiness.missing_tools),
        "missing_access": list(readiness.missing_access),
        "missing_effects": list(readiness.missing_effects),
        "unsupported_surfaces": list(readiness.unsupported_surfaces),
        "unsupported_platforms": list(readiness.unsupported_platforms),
        "checks": [dict(check) for check in current.checks],
    }


def removed_readiness_changed_payload(
    *,
    package: SkillPackageIndex,
    previous: SkillReadinessSnapshot | None,
    current: SkillReadinessSnapshot,
) -> dict[str, object]:
    return {
        "skill": package.skill_id,
        "skill_name": package.name,
        "source": package.source_id,
        "path": package.root_uri,
        "previous_status": previous.status.value if previous is not None else "",
        "status": current.status.value,
        "ready": False,
        "readiness_scope": "catalog",
        "reason": current.reason or "removed",
        "missing_tools": [],
        "missing_access": [],
        "missing_effects": [],
        "unsupported_surfaces": [],
        "unsupported_platforms": [],
        "checks": [dict(check) for check in current.checks],
    }


def _package_root(package: SkillPackage) -> str:
    root_path = package.root_path.rstrip("/")
    if not root_path:
        return ""
    return root_path.rsplit("/", 1)[0] if "/" in root_path else root_path


def _prompt_snapshot_status(readiness: ResolvedSkillReadiness) -> DomainSkillReadinessStatus:
    if readiness.ready:
        return DomainSkillReadinessStatus.READY
    if readiness.unsupported_platforms:
        return DomainSkillReadinessStatus.UNSUPPORTED
    return DomainSkillReadinessStatus.SETUP_NEEDED
