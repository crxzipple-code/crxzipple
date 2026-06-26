from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crxzipple.modules.settings.domain.entities import (
    SettingsOverride,
    SettingsResource,
    SettingsResourceVersion,
)
from crxzipple.modules.settings.domain.exceptions import (
    SettingsConflictError,
    SettingsNotFoundError,
)
from crxzipple.modules.settings.domain.repositories import (
    SettingsActionAuditRepository,
    SettingsOverrideRepository,
    SettingsResourceRepository,
    SettingsResourceVersionRepository,
)


JsonObject = dict[str, Any]


def ensure_active_version_matches(
    resource: SettingsResource,
    *,
    expected_active_version_id: str | None,
    audit_repository: SettingsActionAuditRepository,
    audit_id: str,
) -> None:
    expected = optional_text(expected_active_version_id)
    if expected is None:
        return
    actual = resource.active_version_id
    if actual == expected:
        return
    error: JsonObject = {
        "code": "settings_active_version_conflict",
        "resource_id": resource.id,
        "expected_active_version_id": expected,
        "actual_active_version_id": actual,
    }
    audit_repository.mark_failed(audit_id, error=error)
    raise SettingsConflictError(
        "settings resource active version conflict: "
        f"expected {expected!r}, found {actual!r}.",
    )


def next_version_number(versions: tuple[SettingsResourceVersion, ...]) -> int:
    if not versions:
        return 1
    return max(version.version_number for version in versions) + 1


def require_resource(
    repository: SettingsResourceRepository,
    resource_id: str,
) -> SettingsResource:
    normalized = required_text(resource_id, "resource id")
    resource = repository.get(normalized)
    if resource is None:
        raise SettingsNotFoundError(f"settings resource '{normalized}' was not found.")
    return resource


def latest_published_versions_for_resources(
    repository: SettingsResourceVersionRepository,
    resource_ids: tuple[str, ...],
) -> dict[str, SettingsResourceVersion]:
    batch_reader = getattr(repository, "latest_published_for_resources", None)
    if callable(batch_reader):
        return dict(batch_reader(resource_ids))
    return {
        resource_id: version
        for resource_id in resource_ids
        for version in (repository.latest_published_for_resource(resource_id),)
        if version is not None
    }


def active_overrides_for_resources(
    repository: SettingsOverrideRepository,
    resource_ids: tuple[str, ...],
    *,
    environment: str | None,
) -> dict[str, tuple[SettingsOverride, ...]]:
    batch_reader = getattr(repository, "list_for_resources", None)
    if callable(batch_reader):
        return {
            resource_id: tuple(items)
            for resource_id, items in batch_reader(
                resource_ids,
                environment=environment,
                enabled_only=True,
            ).items()
        }
    return {
        resource_id: repository.list_for_resource(
            resource_id,
            environment=environment,
            enabled_only=True,
        )
        for resource_id in resource_ids
    }


def required_text(value: str | None, field_name: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} is required.")
    return normalized


def optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def deep_merge(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> JsonObject:
    merged: JsonObject = dict(base)
    for key, value in overlay.items():
        if (
            isinstance(value, Mapping)
            and isinstance(merged.get(key), Mapping)
        ):
            merged[str(key)] = deep_merge(merged[key], value)  # type: ignore[index]
        else:
            merged[str(key)] = value
    return merged
