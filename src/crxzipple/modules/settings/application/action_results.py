from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crxzipple.modules.settings.application.models import SettingsActionResult
from crxzipple.modules.settings.domain.entities import (
    SettingsActionAudit,
    SettingsEffectiveSnapshot,
    SettingsOverride,
    SettingsResource,
    SettingsResourceVersion,
)
from crxzipple.modules.settings.domain.value_objects import SettingsValidationResult
from crxzipple.shared.settings import ConfigResolution


JsonObject = dict[str, Any]


def validation_error_payload(validation: SettingsValidationResult) -> JsonObject:
    return {"validation": validation.to_payload()}


def validation_failed_action_result(
    *,
    audit: SettingsActionAudit,
    validation: SettingsValidationResult,
    resource: SettingsResource | None = None,
    version: SettingsResourceVersion | None = None,
) -> SettingsActionResult:
    return SettingsActionResult(
        status="validation_failed",
        audit=audit,
        resource=resource,
        version=version,
        validation=validation,
        warnings=validation.warnings,
    )


def resource_version_result_payload(
    *,
    resource: SettingsResource,
    version: SettingsResourceVersion,
    snapshot: SettingsEffectiveSnapshot | None,
) -> JsonObject:
    return {
        "resource": resource.to_payload(),
        "version": version.to_payload(),
        "snapshot_id": snapshot.id if snapshot is not None else None,
    }


def resource_version_action_result(
    *,
    audit: SettingsActionAudit,
    resource: SettingsResource,
    version: SettingsResourceVersion,
    validation: SettingsValidationResult,
    snapshot: SettingsEffectiveSnapshot | None = None,
    resolution: ConfigResolution[Mapping[str, Any]] | None = None,
) -> SettingsActionResult:
    return SettingsActionResult(
        status="succeeded",
        audit=audit,
        resource=resource,
        version=version,
        snapshot=snapshot,
        resolution=resolution,
        validation=validation,
        warnings=validation.warnings,
    )


def resource_result_payload(resource: SettingsResource) -> JsonObject:
    return {"resource": resource.to_payload()}


def resource_action_result(
    *,
    audit: SettingsActionAudit,
    resource: SettingsResource,
) -> SettingsActionResult:
    return SettingsActionResult(
        status="succeeded",
        audit=audit,
        resource=resource,
    )


def override_result_payload(override: SettingsOverride) -> JsonObject:
    return {"override": override.to_payload()}


def override_action_result(
    *,
    audit: SettingsActionAudit,
    resource: SettingsResource,
    override: SettingsOverride,
    validation: SettingsValidationResult | None = None,
) -> SettingsActionResult:
    return SettingsActionResult(
        status="succeeded",
        audit=audit,
        resource=resource,
        override=override,
        validation=validation or SettingsValidationResult(),
        warnings=validation.warnings if validation is not None else (),
    )
