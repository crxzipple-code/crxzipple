from __future__ import annotations

from typing import Any

from crxzipple.modules.settings.application.action_audit import (
    record_settings_action_attempt,
)
from crxzipple.modules.settings.application.resource_actions import SettingsResourceActions
from crxzipple.modules.settings.application.query_service import SettingsQueryService
from crxzipple.modules.settings.application.resolution_service import (
    SettingsEffectiveResolutionService,
)
from crxzipple.modules.settings.application.override_actions import SettingsOverrideActions
from crxzipple.modules.settings.application.models import (
    CreateSettingsResourceInput,
    PublishSettingsVersionInput,
    RollbackSettingsResourceInput,
    SettingsActionResult,
    SetSettingsOverrideEnabledInput,
    SetSettingsResourceEnabledInput,
    UpdateSettingsResourceInput,
    UpsertSettingsOverrideInput,
)
from crxzipple.modules.settings.domain.repositories import (
    SettingsActionAuditRepository,
    SettingsEffectiveSnapshotRepository,
    SettingsOverrideRepository,
    SettingsResourceRepository,
    SettingsResourceVersionRepository,
)


JsonObject = dict[str, Any]


__all__ = (
    "SettingsActionService",
    "SettingsEffectiveResolutionService",
    "SettingsQueryService",
)


class SettingsActionService:
    def __init__(
        self,
        *,
        resource_repository: SettingsResourceRepository,
        version_repository: SettingsResourceVersionRepository,
        override_repository: SettingsOverrideRepository,
        snapshot_repository: SettingsEffectiveSnapshotRepository,
        audit_repository: SettingsActionAuditRepository,
        resolver: SettingsEffectiveResolutionService | None = None,
    ) -> None:
        self._audits = audit_repository
        resolver = resolver or SettingsEffectiveResolutionService(
            resource_repository=resource_repository,
            version_repository=version_repository,
            override_repository=override_repository,
            snapshot_repository=snapshot_repository,
        )
        self._resource_actions = SettingsResourceActions(
            resource_repository=resource_repository,
            version_repository=version_repository,
            snapshot_repository=snapshot_repository,
            audit_repository=audit_repository,
            resolver=resolver,
        )
        self._override_actions = SettingsOverrideActions(
            resource_repository=resource_repository,
            override_repository=override_repository,
            audit_repository=audit_repository,
        )

    def create_resource(self, data: CreateSettingsResourceInput) -> SettingsActionResult:
        return self._resource_actions.create_resource(data)

    def update_resource(self, data: UpdateSettingsResourceInput) -> SettingsActionResult:
        return self._resource_actions.update_resource(data)

    def publish_version(self, data: PublishSettingsVersionInput) -> SettingsActionResult:
        return self._resource_actions.publish_version(data)

    def rollback_resource(self, data: RollbackSettingsResourceInput) -> SettingsActionResult:
        return self._resource_actions.rollback_resource(data)

    def enable_resource(self, resource_id: str, *, actor: str | None = None, reason: str = "enable settings resource") -> SettingsActionResult:
        return self.set_resource_enabled(
            SetSettingsResourceEnabledInput(
                resource_id=resource_id,
                enabled=True,
                actor=actor,
                reason=reason,
            ),
        )

    def disable_resource(self, resource_id: str, *, actor: str | None = None, reason: str = "disable settings resource") -> SettingsActionResult:
        return self.set_resource_enabled(
            SetSettingsResourceEnabledInput(
                resource_id=resource_id,
                enabled=False,
                actor=actor,
                reason=reason,
            ),
        )

    def set_resource_enabled(self, data: SetSettingsResourceEnabledInput) -> SettingsActionResult:
        return self._resource_actions.set_resource_enabled(data)

    def upsert_override(self, data: UpsertSettingsOverrideInput) -> SettingsActionResult:
        return self._override_actions.upsert_override(data)

    def enable_override(self, override_id: str, *, actor: str | None = None, reason: str = "enable settings override") -> SettingsActionResult:
        return self.set_override_enabled(
            SetSettingsOverrideEnabledInput(
                override_id=override_id,
                enabled=True,
                actor=actor,
                reason=reason,
            ),
        )

    def disable_override(self, override_id: str, *, actor: str | None = None, reason: str = "disable settings override") -> SettingsActionResult:
        return self.set_override_enabled(
            SetSettingsOverrideEnabledInput(
                override_id=override_id,
                enabled=False,
                actor=actor,
                reason=reason,
            ),
        )

    def set_override_enabled(self, data: SetSettingsOverrideEnabledInput) -> SettingsActionResult:
        return self._override_actions.set_override_enabled(data)

    def record_operator_attempt(
        self,
        *,
        action_type: str,
        target_type: str,
        target_id: str | None,
        reason: str,
        actor: str | None = None,
        risk: str | None = None,
        request_metadata: JsonObject | None = None,
    ):
        return self._record_attempt(
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
            reason=reason,
            actor=actor,
            risk=risk,
            request_metadata=request_metadata,
        )

    def mark_operator_attempt_succeeded(
        self,
        audit_id: str,
        *,
        result: JsonObject | None = None,
    ):
        return self._audits.mark_succeeded(audit_id, result=result)

    def mark_operator_attempt_failed(
        self,
        audit_id: str,
        *,
        error: JsonObject,
    ):
        return self._audits.mark_failed(audit_id, error=error)

    def _record_attempt(
        self,
        *,
        action_type: str,
        target_type: str,
        target_id: str | None,
        reason: str,
        actor: str | None = None,
        risk: str | None = None,
        request_metadata: JsonObject | None = None,
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
