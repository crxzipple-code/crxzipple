from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crxzipple.modules.settings.application.resolution_service import (
    SettingsEffectiveResolutionService,
)
from crxzipple.modules.settings.application.service_common import next_version_number
from crxzipple.modules.settings.domain.entities import (
    SettingsEffectiveSnapshot,
    SettingsResource,
    SettingsResourceVersion,
)
from crxzipple.modules.settings.domain.repositories import (
    SettingsEffectiveSnapshotRepository,
    SettingsResourceRepository,
    SettingsResourceVersionRepository,
)
from crxzipple.modules.settings.domain.value_objects import SettingsValidationResult


def build_settings_resource_version(
    version_repository: SettingsResourceVersionRepository,
    *,
    resource: SettingsResource,
    payload: Mapping[str, Any],
    actor: str | None,
    reason: str | None,
    source: str,
    validation: SettingsValidationResult,
) -> SettingsResourceVersion:
    version_number = next_version_number(version_repository.list_for_resource(resource.id))
    return SettingsResourceVersion(
        id=f"{resource.id}:v{version_number}",
        resource_id=resource.id,
        resource_kind=resource.resource_kind,
        payload=dict(payload),
        version_number=version_number,
        validation=validation,
        source=source,
        reason=reason,
        created_by=actor,
    )


def publish_settings_resource_version(
    *,
    resource_repository: SettingsResourceRepository,
    version_repository: SettingsResourceVersionRepository,
    snapshot_repository: SettingsEffectiveSnapshotRepository,
    resolver: SettingsEffectiveResolutionService,
    resource: SettingsResource,
    version: SettingsResourceVersion,
    environment: str | None,
    trace_context: Mapping[str, Any],
) -> SettingsEffectiveSnapshot:
    for existing in version_repository.list_for_resource(resource.id):
        if existing.id != version.id:
            existing.supersede()
            version_repository.save(existing)
    version.publish()
    version_repository.save(version)
    resource.publish(version.id)
    resource_repository.save(resource)
    snapshot = resolver.snapshot(
        resource.id,
        environment=environment,
        trace_context=trace_context,
    )
    snapshot_repository.add(snapshot)
    return snapshot
