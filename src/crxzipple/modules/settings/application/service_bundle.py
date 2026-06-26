from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.settings.application.in_memory import InMemorySettingsRepository
from crxzipple.modules.settings.application.query_service import SettingsQueryService
from crxzipple.modules.settings.application.resolution_service import (
    SettingsEffectiveResolutionService,
)
from crxzipple.modules.settings.application.services import SettingsActionService


@dataclass(frozen=True, slots=True)
class SettingsServices:
    repositories: InMemorySettingsRepository
    actions: SettingsActionService
    queries: SettingsQueryService
    resolver: SettingsEffectiveResolutionService


def create_in_memory_settings_services() -> SettingsServices:
    repositories = InMemorySettingsRepository()
    resolver = SettingsEffectiveResolutionService(
        resource_repository=repositories.resources,
        version_repository=repositories.versions,
        override_repository=repositories.overrides,
        snapshot_repository=repositories.snapshots,
    )
    actions = SettingsActionService(
        resource_repository=repositories.resources,
        version_repository=repositories.versions,
        override_repository=repositories.overrides,
        snapshot_repository=repositories.snapshots,
        audit_repository=repositories.audits,
        resolver=resolver,
    )
    queries = SettingsQueryService(
        resource_repository=repositories.resources,
        version_repository=repositories.versions,
        override_repository=repositories.overrides,
        snapshot_repository=repositories.snapshots,
        audit_repository=repositories.audits,
        resolver=resolver,
    )
    return SettingsServices(
        repositories=repositories,
        actions=actions,
        queries=queries,
        resolver=resolver,
    )
