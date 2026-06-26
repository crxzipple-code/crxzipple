from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crxzipple.modules.settings.application.action_audit import (
    record_settings_action_attempt,
)
from crxzipple.modules.settings.application.action_results import (
    resource_version_action_result,
    resource_version_result_payload,
    validation_error_payload,
    validation_failed_action_result,
)
from crxzipple.modules.settings.application.models import (
    CreateSettingsResourceInput,
    SettingsActionResult,
    UpdateSettingsResourceInput,
)
from crxzipple.modules.settings.application.redaction import redact_value as _redact
from crxzipple.modules.settings.application.resolution_service import (
    SettingsEffectiveResolutionService,
)
from crxzipple.modules.settings.application.resource_versioning import (
    build_settings_resource_version,
    publish_settings_resource_version,
)
from crxzipple.modules.settings.application.service_common import (
    ensure_active_version_matches,
    require_resource,
)
from crxzipple.modules.settings.domain.entities import (
    SettingsEffectiveSnapshot,
    SettingsResource,
)
from crxzipple.modules.settings.domain.exceptions import SettingsAlreadyExistsError
from crxzipple.modules.settings.domain.repositories import (
    SettingsActionAuditRepository,
    SettingsEffectiveSnapshotRepository,
    SettingsResourceRepository,
    SettingsResourceVersionRepository,
)
from crxzipple.modules.settings.domain.value_objects import validate_settings_payload
from crxzipple.shared.settings import ConfigResolution


class SettingsResourceDefinitionActions:
    def __init__(
        self,
        *,
        resource_repository: SettingsResourceRepository,
        version_repository: SettingsResourceVersionRepository,
        snapshot_repository: SettingsEffectiveSnapshotRepository,
        audit_repository: SettingsActionAuditRepository,
        resolver: SettingsEffectiveResolutionService,
    ) -> None:
        self._resources = resource_repository
        self._versions = version_repository
        self._snapshots = snapshot_repository
        self._audits = audit_repository
        self._resolver = resolver

    def create_resource(self, data: CreateSettingsResourceInput) -> SettingsActionResult:
        audit = self._record_attempt(
            action_type="settings.resource.create",
            target_type=data.resource_kind,
            target_id=data.resource_id,
            actor=data.actor,
            reason=data.reason,
            request_metadata={
                "payload": _redact(dict(data.payload)),
                "publish": data.publish,
                "source": data.source,
                "trace_context": dict(data.trace_context),
            },
        )
        validation = validate_settings_payload(data.payload)
        if not validation.ok:
            self._audits.mark_failed(audit.id, error=validation_error_payload(validation))
            return validation_failed_action_result(
                audit=audit,
                validation=validation,
            )
        if self._resources.get(data.resource_id) is not None:
            error = {"code": "settings_resource_exists", "resource_id": data.resource_id}
            self._audits.mark_failed(audit.id, error=error)
            raise SettingsAlreadyExistsError(
                f"settings resource '{data.resource_id}' already exists.",
            )

        resource = SettingsResource(
            id=data.resource_id,
            resource_kind=data.resource_kind,
            owner_module=data.owner_module,
            scope=data.scope,
            display_name=data.display_name,
            metadata=dict(data.metadata),
        )
        version = build_settings_resource_version(
            self._versions,
            resource=resource,
            payload=data.payload,
            actor=data.actor,
            reason=data.reason,
            source=data.source,
            validation=validation,
        )
        self._resources.add(resource)
        self._versions.add(version)

        snapshot: SettingsEffectiveSnapshot | None = None
        resolution: ConfigResolution[Mapping[str, Any]] | None = None
        if data.publish:
            snapshot = publish_settings_resource_version(
                resource_repository=self._resources,
                version_repository=self._versions,
                snapshot_repository=self._snapshots,
                resolver=self._resolver,
                resource=resource,
                version=version,
                environment=None,
                trace_context=data.trace_context,
            )
            resolution = snapshot.to_resolution()

        self._audits.mark_succeeded(
            audit.id,
            result=resource_version_result_payload(
                resource=resource,
                version=version,
                snapshot=snapshot,
            ),
        )
        return resource_version_action_result(
            audit=audit,
            resource=resource,
            version=version,
            snapshot=snapshot,
            resolution=resolution,
            validation=validation,
        )

    def update_resource(self, data: UpdateSettingsResourceInput) -> SettingsActionResult:
        resource = require_resource(self._resources, data.resource_id)
        audit = self._record_attempt(
            action_type="settings.resource.update",
            target_type=resource.resource_kind,
            target_id=resource.id,
            actor=data.actor,
            reason=data.reason,
            request_metadata={
                "payload": _redact(dict(data.payload)),
                "publish": data.publish,
                "source": data.source,
                "trace_context": dict(data.trace_context),
            },
        )
        ensure_active_version_matches(
            resource,
            expected_active_version_id=data.expected_active_version_id,
            audit_repository=self._audits,
            audit_id=audit.id,
        )
        validation = validate_settings_payload(data.payload)
        if not validation.ok:
            self._audits.mark_failed(audit.id, error=validation_error_payload(validation))
            return validation_failed_action_result(
                audit=audit,
                resource=resource,
                validation=validation,
            )

        version = build_settings_resource_version(
            self._versions,
            resource=resource,
            payload=data.payload,
            actor=data.actor,
            reason=data.reason,
            source=data.source,
            validation=validation,
        )
        self._versions.add(version)
        snapshot: SettingsEffectiveSnapshot | None = None
        resolution: ConfigResolution[Mapping[str, Any]] | None = None
        if data.publish:
            snapshot = publish_settings_resource_version(
                resource_repository=self._resources,
                version_repository=self._versions,
                snapshot_repository=self._snapshots,
                resolver=self._resolver,
                resource=resource,
                version=version,
                environment=None,
                trace_context=data.trace_context,
            )
            resolution = snapshot.to_resolution()

        self._audits.mark_succeeded(
            audit.id,
            result=resource_version_result_payload(
                resource=resource,
                version=version,
                snapshot=snapshot,
            ),
        )
        return resource_version_action_result(
            audit=audit,
            resource=resource,
            version=version,
            snapshot=snapshot,
            resolution=resolution,
            validation=validation,
        )

    def _record_attempt(
        self,
        *,
        action_type: str,
        target_type: str,
        target_id: str | None,
        reason: str,
        actor: str | None = None,
        request_metadata: dict[str, Any] | None = None,
    ):
        return record_settings_action_attempt(
            self._audits,
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
            reason=reason,
            actor=actor,
            request_metadata=request_metadata,
        )
