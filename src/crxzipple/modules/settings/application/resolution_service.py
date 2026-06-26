from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from crxzipple.modules.settings.application.service_common import (
    deep_merge,
    optional_text,
    require_resource,
)
from crxzipple.modules.settings.domain.entities import SettingsEffectiveSnapshot
from crxzipple.modules.settings.domain.exceptions import SettingsPublishError
from crxzipple.modules.settings.domain.repositories import (
    SettingsEffectiveSnapshotRepository,
    SettingsOverrideRepository,
    SettingsResourceRepository,
    SettingsResourceVersionRepository,
)
from crxzipple.modules.settings.domain.value_objects import SettingsValidationResult
from crxzipple.shared.settings import ConfigResolution, ConfigSource, SettingsResourceRef


JsonObject = dict[str, Any]


class SettingsEffectiveResolutionService:
    def __init__(
        self,
        *,
        resource_repository: SettingsResourceRepository,
        version_repository: SettingsResourceVersionRepository,
        override_repository: SettingsOverrideRepository,
        snapshot_repository: SettingsEffectiveSnapshotRepository | None = None,
    ) -> None:
        self._resources = resource_repository
        self._versions = version_repository
        self._overrides = override_repository
        self._snapshots = snapshot_repository

    def resolve_effective(
        self,
        resource: SettingsResourceRef,
        *,
        environment: str | None = None,
        trace_context: Mapping[str, Any] | None = None,
    ) -> ConfigResolution[Mapping[str, Any]]:
        return self.resolve(
            resource.resource_id,
            environment=environment,
            trace_context=trace_context,
        )

    def resolve(
        self,
        resource_id: str,
        *,
        environment: str | None = None,
        trace_context: Mapping[str, Any] | None = None,
        persist_snapshot: bool = False,
    ) -> ConfigResolution[Mapping[str, Any]]:
        resource = require_resource(self._resources, resource_id)
        snapshot = self.snapshot(
            resource.id,
            environment=environment,
            trace_context=trace_context,
        )
        if persist_snapshot:
            if self._snapshots is None:
                raise SettingsPublishError("snapshot repository is required to persist resolutions.")
            self._snapshots.add(snapshot)
            return snapshot.to_resolution()
        return snapshot.to_resolution()

    def snapshot(
        self,
        resource_id: str,
        *,
        environment: str | None = None,
        trace_context: Mapping[str, Any] | None = None,
    ) -> SettingsEffectiveSnapshot:
        resource = require_resource(self._resources, resource_id)
        published = self._versions.latest_published_for_resource(resource.id)
        resource_ref = resource.ref()
        value: JsonObject = {}
        sources: list[ConfigSource] = []
        validation = SettingsValidationResult.ok_result()
        version_id: str | None = None

        if published is None:
            validation = SettingsValidationResult(
                ok=True,
                warnings=("resource has no published version.",),
            )
        else:
            value = dict(published.payload)
            version_id = published.id
            sources.append(published.to_source(resource=resource_ref))

        value["enabled"] = resource.enabled
        sources.append(
            ConfigSource(
                source_id=f"resource:{resource.id}:state",
                source_kind="resource_state",
                resource=resource_ref,
                value={"enabled": resource.enabled, "status": resource.status.value},
            ),
        )

        applied_overrides: list[ConfigSource] = []
        normalized_environment = optional_text(environment)
        if normalized_environment is not None:
            for override in self._overrides.list_for_resource(
                resource.id,
                environment=normalized_environment,
                enabled_only=True,
            ):
                value = deep_merge(value, override.values)
                source = override.to_source(resource=resource_ref)
                sources.append(source)
                applied_overrides.append(source)

        return SettingsEffectiveSnapshot(
            id=f"snapshot_{uuid4().hex}",
            resource=resource_ref,
            effective_value=value,
            sources=tuple(sources),
            overrides=tuple(applied_overrides),
            environment=normalized_environment,
            version_id=version_id,
            validation=validation,
            metadata={"trace_context": dict(trace_context or {})},
        )
