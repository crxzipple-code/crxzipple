from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from crxzipple.modules.settings.domain.entities import (
    SettingsActionAudit,
    SettingsEffectiveSnapshot,
    SettingsOverride,
    SettingsResource,
    SettingsResourceVersion,
)
from crxzipple.modules.settings.domain.exceptions import (
    SettingsAlreadyExistsError,
    SettingsNotFoundError,
)
from crxzipple.modules.settings.domain.value_objects import SettingsVersionStatus


@dataclass(slots=True)
class InMemorySettingsResourceRepository:
    resources: dict[str, SettingsResource] = field(default_factory=dict)

    def add(self, resource: SettingsResource) -> None:
        if resource.id in self.resources:
            raise SettingsAlreadyExistsError(
                f"settings resource '{resource.id}' already exists.",
            )
        self.resources[resource.id] = resource

    def save(self, resource: SettingsResource) -> None:
        self.resources[resource.id] = resource

    def get(self, resource_id: str) -> SettingsResource | None:
        return self.resources.get(resource_id)

    def list(
        self,
        *,
        resource_kind: str | None = None,
        owner_module: str | None = None,
    ) -> tuple[SettingsResource, ...]:
        resources = list(self.resources.values())
        if resource_kind is not None:
            normalized_kind = resource_kind.strip()
            resources = [
                resource
                for resource in resources
                if resource.resource_kind == normalized_kind
            ]
        if owner_module is not None:
            normalized_owner = owner_module.strip()
            resources = [
                resource
                for resource in resources
                if resource.owner_module == normalized_owner
            ]
        return tuple(sorted(resources, key=lambda resource: (resource.resource_kind, resource.id)))


@dataclass(slots=True)
class InMemorySettingsResourceVersionRepository:
    versions: dict[str, SettingsResourceVersion] = field(default_factory=dict)

    def add(self, version: SettingsResourceVersion) -> None:
        if version.id in self.versions:
            raise SettingsAlreadyExistsError(
                f"settings version '{version.id}' already exists.",
            )
        self.versions[version.id] = version

    def save(self, version: SettingsResourceVersion) -> None:
        self.versions[version.id] = version

    def get(self, version_id: str) -> SettingsResourceVersion | None:
        return self.versions.get(version_id)

    def list_for_resource(self, resource_id: str) -> tuple[SettingsResourceVersion, ...]:
        return tuple(
            sorted(
                [
                    version
                    for version in self.versions.values()
                    if version.resource_id == resource_id
                ],
                key=lambda version: version.version_number,
            ),
        )

    def latest_for_resource(self, resource_id: str) -> SettingsResourceVersion | None:
        versions = self.list_for_resource(resource_id)
        if not versions:
            return None
        return versions[-1]

    def latest_published_for_resource(
        self,
        resource_id: str,
    ) -> SettingsResourceVersion | None:
        published = [
            version
            for version in self.list_for_resource(resource_id)
            if version.status is SettingsVersionStatus.PUBLISHED
        ]
        if not published:
            return None
        return sorted(
            published,
            key=lambda version: (version.published_at or version.created_at, version.version_number),
        )[-1]

    def latest_published_for_resources(
        self,
        resource_ids: tuple[str, ...],
    ) -> dict[str, SettingsResourceVersion]:
        return {
            resource_id: version
            for resource_id in resource_ids
            for version in (self.latest_published_for_resource(resource_id),)
            if version is not None
        }


@dataclass(slots=True)
class InMemorySettingsOverrideRepository:
    overrides: dict[str, SettingsOverride] = field(default_factory=dict)

    def add(self, override: SettingsOverride) -> None:
        if override.id in self.overrides:
            raise SettingsAlreadyExistsError(
                f"settings override '{override.id}' already exists.",
            )
        self.overrides[override.id] = override

    def save(self, override: SettingsOverride) -> None:
        self.overrides[override.id] = override

    def get(self, override_id: str) -> SettingsOverride | None:
        return self.overrides.get(override_id)

    def list_for_resource(
        self,
        resource_id: str,
        *,
        environment: str | None = None,
        enabled_only: bool = False,
    ) -> tuple[SettingsOverride, ...]:
        overrides = [
            override
            for override in self.overrides.values()
            if override.resource_id == resource_id
        ]
        if environment is not None:
            normalized_environment = environment.strip()
            overrides = [
                override
                for override in overrides
                if override.environment == normalized_environment
            ]
        if enabled_only:
            overrides = [override for override in overrides if override.enabled]
        return tuple(sorted(overrides, key=lambda override: (override.priority, override.id)))

    def list_for_resources(
        self,
        resource_ids: tuple[str, ...],
        *,
        environment: str | None = None,
        enabled_only: bool = False,
    ) -> dict[str, tuple[SettingsOverride, ...]]:
        return {
            resource_id: self.list_for_resource(
                resource_id,
                environment=environment,
                enabled_only=enabled_only,
            )
            for resource_id in resource_ids
        }


@dataclass(slots=True)
class InMemorySettingsEffectiveSnapshotRepository:
    snapshots: dict[str, SettingsEffectiveSnapshot] = field(default_factory=dict)

    def add(self, snapshot: SettingsEffectiveSnapshot) -> None:
        self.snapshots[snapshot.id] = snapshot

    def get(self, snapshot_id: str) -> SettingsEffectiveSnapshot | None:
        return self.snapshots.get(snapshot_id)

    def latest_for_resource(
        self,
        resource_id: str,
        *,
        environment: str | None = None,
    ) -> SettingsEffectiveSnapshot | None:
        snapshots = [
            snapshot
            for snapshot in self.snapshots.values()
            if snapshot.resource.resource_id == resource_id
        ]
        if environment is not None:
            normalized_environment = environment.strip()
            snapshots = [
                snapshot
                for snapshot in snapshots
                if snapshot.environment == normalized_environment
            ]
        if not snapshots:
            return None
        return sorted(snapshots, key=lambda snapshot: snapshot.created_at)[-1]


@dataclass(slots=True)
class InMemorySettingsActionAuditRepository:
    audits: dict[str, SettingsActionAudit] = field(default_factory=dict)

    def record_attempt(
        self,
        *,
        action_type: str,
        target_type: str,
        target_id: str | None,
        reason: str,
        actor: str | None = None,
        risk: str | None = None,
        request_metadata: dict[str, Any] | None = None,
    ) -> SettingsActionAudit:
        audit = SettingsActionAudit(
            id=f"settings_audit_{uuid4().hex}",
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
            reason=reason,
            actor=actor,
            risk=risk,
            request_metadata=request_metadata or {},
        )
        self.audits[audit.id] = audit
        return audit

    def mark_succeeded(
        self,
        audit_id: str,
        *,
        result: dict[str, Any] | None = None,
    ) -> SettingsActionAudit:
        audit = self._require(audit_id)
        audit.mark_succeeded(result=result)
        return audit

    def mark_failed(
        self,
        audit_id: str,
        *,
        error: dict[str, Any],
    ) -> SettingsActionAudit:
        audit = self._require(audit_id)
        audit.mark_failed(error=error)
        return audit

    def get(self, audit_id: str) -> SettingsActionAudit | None:
        return self.audits.get(audit_id)

    def list(self) -> tuple[SettingsActionAudit, ...]:
        return tuple(sorted(self.audits.values(), key=lambda audit: audit.created_at))

    def _require(self, audit_id: str) -> SettingsActionAudit:
        audit = self.audits.get(audit_id)
        if audit is None:
            raise SettingsNotFoundError(f"settings audit '{audit_id}' was not found.")
        return audit


@dataclass(slots=True)
class InMemorySettingsRepository:
    resources: InMemorySettingsResourceRepository = field(
        default_factory=InMemorySettingsResourceRepository,
    )
    versions: InMemorySettingsResourceVersionRepository = field(
        default_factory=InMemorySettingsResourceVersionRepository,
    )
    overrides: InMemorySettingsOverrideRepository = field(
        default_factory=InMemorySettingsOverrideRepository,
    )
    snapshots: InMemorySettingsEffectiveSnapshotRepository = field(
        default_factory=InMemorySettingsEffectiveSnapshotRepository,
    )
    audits: InMemorySettingsActionAuditRepository = field(
        default_factory=InMemorySettingsActionAuditRepository,
    )
