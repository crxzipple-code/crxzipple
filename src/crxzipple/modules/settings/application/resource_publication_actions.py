from __future__ import annotations

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
    PublishSettingsVersionInput,
    RollbackSettingsResourceInput,
    SettingsActionResult,
)
from crxzipple.modules.settings.application.resolution_service import (
    SettingsEffectiveResolutionService,
)
from crxzipple.modules.settings.application.resource_versioning import (
    publish_settings_resource_version,
)
from crxzipple.modules.settings.application.service_common import (
    ensure_active_version_matches,
    require_resource,
)
from crxzipple.modules.settings.domain.exceptions import SettingsNotFoundError
from crxzipple.modules.settings.domain.repositories import (
    SettingsActionAuditRepository,
    SettingsEffectiveSnapshotRepository,
    SettingsResourceRepository,
    SettingsResourceVersionRepository,
)


class SettingsResourcePublicationActions:
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

    def publish_version(self, data: PublishSettingsVersionInput) -> SettingsActionResult:
        resource = require_resource(self._resources, data.resource_id)
        audit = self._record_attempt(
            action_type="settings.version.publish",
            target_type=resource.resource_kind,
            target_id=resource.id,
            actor=data.actor,
            reason=data.reason,
            risk="configuration_change",
            request_metadata={
                "version_id": data.version_id,
                "expected_active_version_id": data.expected_active_version_id,
                "environment": data.environment,
                "trace_context": dict(data.trace_context),
            },
        )
        ensure_active_version_matches(
            resource,
            expected_active_version_id=data.expected_active_version_id,
            audit_repository=self._audits,
            audit_id=audit.id,
        )
        version = (
            self._versions.get(data.version_id)
            if data.version_id is not None
            else self._versions.latest_for_resource(resource.id)
        )
        if version is None or version.resource_id != resource.id:
            self._audits.mark_failed(
                audit.id,
                error={
                    "code": "settings_version_not_found",
                    "version_id": data.version_id,
                },
            )
            raise SettingsNotFoundError("settings version was not found for resource.")
        if not version.validation.ok:
            self._audits.mark_failed(
                audit.id,
                error=validation_error_payload(version.validation),
            )
            return validation_failed_action_result(
                audit=audit,
                resource=resource,
                version=version,
                validation=version.validation,
            )

        snapshot = publish_settings_resource_version(
            resource_repository=self._resources,
            version_repository=self._versions,
            snapshot_repository=self._snapshots,
            resolver=self._resolver,
            resource=resource,
            version=version,
            environment=data.environment,
            trace_context=data.trace_context,
        )
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
            resolution=snapshot.to_resolution(),
            validation=version.validation,
        )

    def rollback_resource(
        self,
        data: RollbackSettingsResourceInput,
    ) -> SettingsActionResult:
        resource = require_resource(self._resources, data.resource_id)
        audit = self._record_attempt(
            action_type="settings.resource.rollback",
            target_type=resource.resource_kind,
            target_id=resource.id,
            actor=data.actor,
            reason=data.reason,
            risk="configuration_rollback",
            request_metadata={
                "target_version_id": data.target_version_id,
                "expected_active_version_id": data.expected_active_version_id,
                "environment": data.environment,
                "trace_context": dict(data.trace_context),
            },
        )
        ensure_active_version_matches(
            resource,
            expected_active_version_id=data.expected_active_version_id,
            audit_repository=self._audits,
            audit_id=audit.id,
        )
        target = self._versions.get(data.target_version_id)
        if target is None or target.resource_id != resource.id:
            self._audits.mark_failed(
                audit.id,
                error={
                    "code": "settings_rollback_target_not_found",
                    "target_version_id": data.target_version_id,
                },
            )
            raise SettingsNotFoundError("rollback target version was not found for resource.")
        if not target.validation.ok:
            self._audits.mark_failed(
                audit.id,
                error=validation_error_payload(target.validation),
            )
            return validation_failed_action_result(
                audit=audit,
                resource=resource,
                version=target,
                validation=target.validation,
            )

        snapshot = publish_settings_resource_version(
            resource_repository=self._resources,
            version_repository=self._versions,
            snapshot_repository=self._snapshots,
            resolver=self._resolver,
            resource=resource,
            version=target,
            environment=data.environment,
            trace_context=data.trace_context,
        )
        self._audits.mark_succeeded(
            audit.id,
            result=resource_version_result_payload(
                resource=resource,
                version=target,
                snapshot=snapshot,
            ),
        )
        return resource_version_action_result(
            audit=audit,
            resource=resource,
            version=target,
            snapshot=snapshot,
            resolution=snapshot.to_resolution(),
            validation=target.validation,
        )

    def _record_attempt(
        self,
        *,
        action_type: str,
        target_type: str,
        target_id: str | None,
        reason: str,
        actor: str | None = None,
        risk: str | None = None,
        request_metadata: dict[str, Any] | None = None,
    ):
        return record_settings_action_attempt(
            self._audits,
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
            reason=reason,
            actor=actor,
            risk=risk,
            request_metadata=request_metadata,
        )
