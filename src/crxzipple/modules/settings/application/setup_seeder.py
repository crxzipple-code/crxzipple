from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crxzipple.modules.settings.application.service_bundle import SettingsServices
from crxzipple.modules.settings.application.setup_payloads import (
    effective_payload_matches_seed,
)
from crxzipple.modules.settings.application.setup_resources import (
    SETTINGS_GOVERNANCE_RESOURCE_KINDS,
    collect_core_settings_resources,
)
from crxzipple.modules.settings.application.setup_results import (
    SettingsBootstrapImportResult,
)
from crxzipple.modules.settings.domain.entities import (
    SettingsResource,
    SettingsResourceVersion,
)
from crxzipple.modules.settings.domain.exceptions import SettingsAlreadyExistsError
from crxzipple.modules.settings.domain.value_objects import validate_settings_payload


def seed_core_settings_resources(
    settings: object,
    *,
    services: SettingsServices,
) -> SettingsBootstrapImportResult:
    counts = {kind: 0 for kind in SETTINGS_GOVERNANCE_RESOURCE_KINDS}
    created = 0
    updated = 0
    skipped = 0

    for seed in collect_core_settings_resources(settings):
        counts[seed.ref.resource_kind] = counts.get(seed.ref.resource_kind, 0) + 1
        existing = services.repositories.resources.get(seed.ref.resource_id)
        if existing is not None:
            result = _seed_existing_resource(services, existing=existing, seed=seed)
            skipped += result.skipped
            updated += result.updated
            continue
        _seed_new_resource(services, seed=seed)
        created += 1

    return SettingsBootstrapImportResult(
        imported_counts=counts,
        created=created,
        updated=updated,
        skipped=skipped,
    )


class _SeedExistingResult:
    def __init__(self, *, updated: int = 0, skipped: int = 0) -> None:
        self.updated = updated
        self.skipped = skipped


def _seed_existing_resource(
    services: SettingsServices,
    *,
    existing: SettingsResource,
    seed,
) -> _SeedExistingResult:
    if existing.resource_kind != seed.ref.resource_kind:
        return _SeedExistingResult(skipped=1)
    if seed.ref.resource_kind == "runtime-defaults":
        return _SeedExistingResult(skipped=1)
    if effective_payload_matches_seed(services.queries, existing.id, seed.payload):
        return _SeedExistingResult(skipped=1)
    validation = validate_settings_payload(seed.payload)
    existing.owner_module = seed.ref.owner_module
    existing.scope = seed.ref.scope
    existing.display_name = seed.ref.display_name
    existing.metadata = seed.metadata
    version = _add_seed_update_version(
        services,
        resource=existing,
        payload=seed.payload,
        validation=validation,
        source=seed.source,
        metadata=seed.metadata,
    )
    if version is None:
        return _SeedExistingResult(skipped=1)
    services.repositories.resources.save(existing)
    if validation.ok:
        snapshot = services.resolver.snapshot(
            existing.id,
            trace_context={"bootstrap_source": seed.source},
        )
        services.repositories.snapshots.add(snapshot)
    return _SeedExistingResult(updated=1)


def _seed_new_resource(services: SettingsServices, *, seed) -> None:
    validation = validate_settings_payload(seed.payload)
    resource = SettingsResource(
        id=seed.ref.resource_id,
        resource_kind=seed.ref.resource_kind,
        owner_module=seed.ref.owner_module,
        scope=seed.ref.scope,
        display_name=seed.ref.display_name,
        metadata=seed.metadata,
    )
    version = SettingsResourceVersion(
        id=f"{seed.ref.resource_id}:v1",
        resource_id=seed.ref.resource_id,
        resource_kind=seed.ref.resource_kind,
        payload=seed.payload,
        version_number=1,
        validation=validation,
        source=seed.source,
        reason="bootstrap settings seed",
        created_by="system",
        metadata=seed.metadata,
    )
    if validation.ok:
        version.publish()
        resource.publish(version.id)
    services.repositories.resources.add(resource)
    services.repositories.versions.add(version)
    if validation.ok:
        snapshot = services.resolver.snapshot(
            resource.id,
            trace_context={"bootstrap_source": seed.source},
        )
        services.repositories.snapshots.add(snapshot)


def _add_seed_update_version(
    services: SettingsServices,
    *,
    resource: SettingsResource,
    payload: Mapping[str, Any],
    validation: Any,
    source: str,
    metadata: Mapping[str, Any],
) -> SettingsResourceVersion | None:
    for _attempt in range(3):
        versions = services.repositories.versions.list_for_resource(resource.id)
        version = SettingsResourceVersion(
            id=_next_seed_version_id(resource.id, versions),
            resource_id=resource.id,
            resource_kind=resource.resource_kind,
            payload=payload,
            version_number=_next_seed_version_number(versions),
            validation=validation,
            source=source,
            reason="bootstrap settings seed",
            created_by="system",
            metadata=metadata,
        )
        if validation.ok:
            version.publish()
            resource.publish(version.id)
        try:
            services.repositories.versions.add(version)
            return version
        except SettingsAlreadyExistsError:
            if effective_payload_matches_seed(services.queries, resource.id, payload):
                return None
    services.repositories.versions.add(version)
    return version


def _next_seed_version_id(
    resource_id: str,
    versions: tuple[SettingsResourceVersion, ...],
) -> str:
    return f"{resource_id}:v{_next_seed_version_number(versions)}"


def _next_seed_version_number(
    versions: tuple[SettingsResourceVersion, ...],
) -> int:
    if not versions:
        return 1
    return max(version.version_number for version in versions) + 1
