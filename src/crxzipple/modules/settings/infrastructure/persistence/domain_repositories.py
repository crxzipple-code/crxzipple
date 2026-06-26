from __future__ import annotations

from dataclasses import dataclass

from crxzipple.core.db import SessionFactory
from crxzipple.modules.settings.application.services import (
    SettingsActionService,
    SettingsEffectiveResolutionService,
    SettingsQueryService,
)
from crxzipple.modules.settings.application.service_bundle import SettingsServices
from crxzipple.modules.settings.infrastructure.persistence.domain_action_audit_repository import (
    SqlAlchemySettingsActionAuditDomainRepository,
)
from crxzipple.modules.settings.infrastructure.persistence.domain_override_repository import (
    SqlAlchemySettingsOverrideRepository,
)
from crxzipple.modules.settings.infrastructure.persistence.domain_resource_repository import (
    SqlAlchemySettingsResourceRepository,
)
from crxzipple.modules.settings.infrastructure.persistence.domain_snapshot_repository import (
    SqlAlchemySettingsEffectiveSnapshotRepository,
)
from crxzipple.modules.settings.infrastructure.persistence.domain_version_repository import (
    SqlAlchemySettingsResourceVersionRepository,
)

@dataclass(slots=True)
class SqlAlchemySettingsRepositories:
    resources: "SqlAlchemySettingsResourceRepository"
    versions: "SqlAlchemySettingsResourceVersionRepository"
    overrides: "SqlAlchemySettingsOverrideRepository"
    snapshots: "SqlAlchemySettingsEffectiveSnapshotRepository"
    audits: "SqlAlchemySettingsActionAuditDomainRepository"


def create_sqlalchemy_settings_services(
    session_factory: SessionFactory,
) -> SettingsServices:
    repositories = SqlAlchemySettingsRepositories(
        resources=SqlAlchemySettingsResourceRepository(session_factory),
        versions=SqlAlchemySettingsResourceVersionRepository(session_factory),
        overrides=SqlAlchemySettingsOverrideRepository(session_factory),
        snapshots=SqlAlchemySettingsEffectiveSnapshotRepository(session_factory),
        audits=SqlAlchemySettingsActionAuditDomainRepository(session_factory),
    )
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
        repositories=repositories,  # type: ignore[arg-type]
        actions=actions,
        queries=queries,
        resolver=resolver,
    )
