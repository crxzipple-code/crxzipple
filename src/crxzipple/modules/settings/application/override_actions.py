from __future__ import annotations

from uuid import uuid4

from crxzipple.modules.settings.application.action_audit import (
    record_settings_action_attempt,
)
from crxzipple.modules.settings.application.action_results import (
    override_action_result,
    override_result_payload,
    validation_error_payload,
    validation_failed_action_result,
)
from crxzipple.modules.settings.application.models import (
    SettingsActionResult,
    SetSettingsOverrideEnabledInput,
    UpsertSettingsOverrideInput,
)
from crxzipple.modules.settings.application.redaction import redact_value as _redact
from crxzipple.modules.settings.application.service_common import require_resource
from crxzipple.modules.settings.domain.entities import SettingsOverride
from crxzipple.modules.settings.domain.exceptions import (
    SettingsNotFoundError,
    SettingsPublishError,
)
from crxzipple.modules.settings.domain.repositories import (
    SettingsActionAuditRepository,
    SettingsOverrideRepository,
    SettingsResourceRepository,
)
from crxzipple.modules.settings.domain.value_objects import validate_settings_payload


class SettingsOverrideActions:
    def __init__(
        self,
        *,
        resource_repository: SettingsResourceRepository,
        override_repository: SettingsOverrideRepository,
        audit_repository: SettingsActionAuditRepository,
    ) -> None:
        self._resources = resource_repository
        self._overrides = override_repository
        self._audits = audit_repository

    def upsert_override(
        self,
        data: UpsertSettingsOverrideInput,
    ) -> SettingsActionResult:
        resource = require_resource(self._resources, data.resource_id)
        action_type = "settings.override.create"
        existing = self._overrides.get(data.override_id) if data.override_id is not None else None
        if existing is not None:
            action_type = "settings.override.update"
        audit = record_settings_action_attempt(
            self._audits,
            action_type=action_type,
            target_type=resource.resource_kind,
            target_id=resource.id,
            actor=data.actor,
            reason=data.reason,
            risk="configuration_override",
            request_metadata={
                "override_id": data.override_id,
                "environment": data.environment,
                "values": _redact(dict(data.values)),
                "trace_context": dict(data.trace_context),
            },
        )
        validation = validate_settings_payload(data.values)
        if not validation.ok:
            self._audits.mark_failed(audit.id, error=validation_error_payload(validation))
            return validation_failed_action_result(
                audit=audit,
                resource=resource,
                validation=validation,
            )

        if existing is None:
            override = SettingsOverride(
                id=data.override_id or f"override_{uuid4().hex}",
                resource_id=resource.id,
                resource_kind=resource.resource_kind,
                environment=data.environment,
                values=data.values,
                enabled=data.enabled,
                priority=data.priority,
                reason=data.reason,
                created_by=data.actor,
                metadata=dict(data.metadata),
            )
            self._overrides.add(override)
        else:
            if existing.resource_id != resource.id:
                self._audits.mark_failed(
                    audit.id,
                    error={"code": "override_resource_mismatch", "override_id": existing.id},
                )
                raise SettingsPublishError(
                    "override belongs to a different settings resource.",
                )
            existing.update_values(data.values, reason=data.reason)
            existing.enabled = data.enabled
            existing.priority = data.priority
            self._overrides.save(existing)
            override = existing
        self._audits.mark_succeeded(audit.id, result=override_result_payload(override))
        return override_action_result(
            audit=audit,
            resource=resource,
            override=override,
            validation=validation,
        )

    def set_override_enabled(
        self,
        data: SetSettingsOverrideEnabledInput,
    ) -> SettingsActionResult:
        override = self._overrides.get(data.override_id)
        if override is None:
            raise SettingsNotFoundError(
                f"settings override '{data.override_id}' was not found.",
            )
        resource = require_resource(self._resources, override.resource_id)
        audit = record_settings_action_attempt(
            self._audits,
            action_type=(
                "settings.override.enable" if data.enabled else "settings.override.disable"
            ),
            target_type=resource.resource_kind,
            target_id=resource.id,
            actor=data.actor,
            reason=data.reason,
            request_metadata={
                "override_id": override.id,
                "trace_context": dict(data.trace_context),
            },
        )
        if data.enabled:
            override.enable()
        else:
            override.disable()
        self._overrides.save(override)
        self._audits.mark_succeeded(audit.id, result=override_result_payload(override))
        return override_action_result(
            audit=audit,
            resource=resource,
            override=override,
        )
