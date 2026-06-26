from __future__ import annotations

from typing import Any

from crxzipple.modules.settings.application.action_audit import (
    record_settings_action_attempt,
)
from crxzipple.modules.settings.application.action_results import (
    resource_action_result,
    resource_result_payload,
)
from crxzipple.modules.settings.application.models import (
    CreateSettingsResourceInput,
    PublishSettingsVersionInput,
    RollbackSettingsResourceInput,
    SettingsActionResult,
    SetSettingsResourceEnabledInput,
    UpdateSettingsResourceInput,
)
from crxzipple.modules.settings.application.resource_definition_actions import (
    SettingsResourceDefinitionActions,
)
from crxzipple.modules.settings.application.resolution_service import (
    SettingsEffectiveResolutionService,
)
from crxzipple.modules.settings.application.resource_publication_actions import (
    SettingsResourcePublicationActions,
)
from crxzipple.modules.settings.application.service_common import require_resource
from crxzipple.modules.settings.domain.repositories import (
    SettingsActionAuditRepository,
    SettingsEffectiveSnapshotRepository,
    SettingsResourceRepository,
    SettingsResourceVersionRepository,
)


class SettingsResourceActions:
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
        self._definition_actions = SettingsResourceDefinitionActions(
            resource_repository=resource_repository,
            version_repository=version_repository,
            snapshot_repository=snapshot_repository,
            audit_repository=audit_repository,
            resolver=resolver,
        )
        self._publication_actions = SettingsResourcePublicationActions(
            resource_repository=resource_repository,
            version_repository=version_repository,
            snapshot_repository=snapshot_repository,
            audit_repository=audit_repository,
            resolver=resolver,
        )

    def create_resource(self, data: CreateSettingsResourceInput) -> SettingsActionResult:
        return self._definition_actions.create_resource(data)

    def update_resource(self, data: UpdateSettingsResourceInput) -> SettingsActionResult:
        return self._definition_actions.update_resource(data)

    def publish_version(self, data: PublishSettingsVersionInput) -> SettingsActionResult:
        return self._publication_actions.publish_version(data)

    def rollback_resource(self, data: RollbackSettingsResourceInput) -> SettingsActionResult:
        return self._publication_actions.rollback_resource(data)

    def set_resource_enabled(
        self,
        data: SetSettingsResourceEnabledInput,
    ) -> SettingsActionResult:
        resource = require_resource(self._resources, data.resource_id)
        audit = self._record_attempt(
            action_type=(
                "settings.resource.enable" if data.enabled else "settings.resource.disable"
            ),
            target_type=resource.resource_kind,
            target_id=resource.id,
            actor=data.actor,
            reason=data.reason,
            request_metadata={"trace_context": dict(data.trace_context)},
        )
        if data.enabled:
            resource.enable()
        else:
            resource.disable()
        self._resources.save(resource)
        self._audits.mark_succeeded(audit.id, result=resource_result_payload(resource))
        return resource_action_result(
            audit=audit,
            resource=resource,
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
