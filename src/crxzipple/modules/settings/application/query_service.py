from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crxzipple.modules.settings.application.resolution_service import (
    SettingsEffectiveResolutionService,
)
from crxzipple.modules.settings.application.service_common import (
    active_overrides_for_resources,
    deep_merge,
    latest_published_versions_for_resources,
    require_resource,
)
from crxzipple.modules.settings.domain.entities import (
    SettingsEffectiveSnapshot,
    SettingsOverride,
    SettingsResource,
    SettingsResourceVersion,
)
from crxzipple.modules.settings.domain.repositories import (
    SettingsActionAuditRepository,
    SettingsEffectiveSnapshotRepository,
    SettingsOverrideRepository,
    SettingsResourceRepository,
    SettingsResourceVersionRepository,
)
from crxzipple.shared.settings import ConfigResolution


JsonObject = dict[str, Any]


class SettingsQueryService:
    def __init__(
        self,
        *,
        resource_repository: SettingsResourceRepository,
        version_repository: SettingsResourceVersionRepository,
        override_repository: SettingsOverrideRepository,
        snapshot_repository: SettingsEffectiveSnapshotRepository,
        audit_repository: SettingsActionAuditRepository,
        resolver: SettingsEffectiveResolutionService | None = None,
    ) -> None:
        self._resources = resource_repository
        self._versions = version_repository
        self._overrides = override_repository
        self._snapshots = snapshot_repository
        self._audits = audit_repository
        self._resolver = resolver or SettingsEffectiveResolutionService(
            resource_repository=resource_repository,
            version_repository=version_repository,
            override_repository=override_repository,
            snapshot_repository=snapshot_repository,
        )

    def get_resource(self, resource_id: str) -> SettingsResource:
        return require_resource(self._resources, resource_id)

    def list_resources(
        self,
        *,
        resource_kind: str | None = None,
        owner_module: str | None = None,
    ) -> tuple[SettingsResource, ...]:
        return self._resources.list(
            resource_kind=resource_kind,
            owner_module=owner_module,
        )

    def list_versions(self, resource_id: str) -> tuple[SettingsResourceVersion, ...]:
        require_resource(self._resources, resource_id)
        return self._versions.list_for_resource(resource_id)

    def get_effective(
        self,
        resource_id: str,
        *,
        environment: str | None = None,
        trace_context: Mapping[str, Any] | None = None,
    ) -> ConfigResolution[Mapping[str, Any]]:
        return self._resolver.resolve(
            resource_id,
            environment=environment,
            trace_context=trace_context,
        )

    def list_effective_payloads(
        self,
        *,
        resource_kind: str,
        environment: str | None = None,
    ) -> tuple[tuple[str, Mapping[str, Any]], ...]:
        resources = self.list_resources(resource_kind=resource_kind)
        if not resources:
            return ()
        resource_ids = tuple(resource.id for resource in resources)
        published_by_resource = latest_published_versions_for_resources(
            self._versions,
            resource_ids,
        )
        overrides_by_resource = active_overrides_for_resources(
            self._overrides,
            resource_ids,
            environment=environment,
        )
        payloads: list[tuple[str, Mapping[str, Any]]] = []
        for resource in resources:
            value: JsonObject = {}
            published = published_by_resource.get(resource.id)
            if published is not None:
                value.update(published.payload)
            value["enabled"] = resource.enabled
            for override in overrides_by_resource.get(resource.id, ()):
                value = deep_merge(value, override.values)
            payloads.append((resource.id, value))
        return tuple(payloads)

    def latest_snapshot(
        self,
        resource_id: str,
        *,
        environment: str | None = None,
    ) -> SettingsEffectiveSnapshot | None:
        return self._snapshots.latest_for_resource(resource_id, environment=environment)

    def list_overrides(
        self,
        resource_id: str,
        *,
        environment: str | None = None,
    ) -> tuple[SettingsOverride, ...]:
        require_resource(self._resources, resource_id)
        return self._overrides.list_for_resource(resource_id, environment=environment)

    def list_audits(self):
        return self._audits.list()
