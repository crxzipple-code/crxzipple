from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

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
from crxzipple.modules.settings.domain.entities import (
    SettingsEffectiveSnapshot,
    SettingsOverride,
    SettingsResource,
    SettingsResourceVersion,
)
from crxzipple.modules.settings.domain.exceptions import (
    SettingsAlreadyExistsError,
    SettingsNotFoundError,
    SettingsPublishError,
)
from crxzipple.modules.settings.domain.repositories import (
    SettingsActionAuditRepository,
    SettingsEffectiveSnapshotRepository,
    SettingsOverrideRepository,
    SettingsResourceRepository,
    SettingsResourceVersionRepository,
)
from crxzipple.modules.settings.domain.value_objects import (
    SettingsValidationResult,
    validate_settings_payload,
)
from crxzipple.shared.settings import ConfigResolution, ConfigSource, SettingsResourceRef


JsonObject = dict[str, Any]


class SettingsEffectiveResolutionService:
    def __init__(
        self,
        *,
        resource_repository: SettingsResourceRepository,
        version_repository: SettingsResourceVersionRepository,
        override_repository: SettingsOverrideRepository,
        snapshot_repository: SettingsEffectiveSnapshotRepository | None = None,
    ) -> None:
        self._resources = resource_repository
        self._versions = version_repository
        self._overrides = override_repository
        self._snapshots = snapshot_repository

    def resolve_effective(
        self,
        resource: SettingsResourceRef,
        *,
        environment: str | None = None,
        trace_context: Mapping[str, Any] | None = None,
    ) -> ConfigResolution[Mapping[str, Any]]:
        return self.resolve(
            resource.resource_id,
            environment=environment,
            trace_context=trace_context,
        )

    def resolve(
        self,
        resource_id: str,
        *,
        environment: str | None = None,
        trace_context: Mapping[str, Any] | None = None,
        persist_snapshot: bool = False,
    ) -> ConfigResolution[Mapping[str, Any]]:
        resource = _require_resource(self._resources, resource_id)
        snapshot = self.snapshot(
            resource.id,
            environment=environment,
            trace_context=trace_context,
        )
        if persist_snapshot:
            if self._snapshots is None:
                raise SettingsPublishError("snapshot repository is required to persist resolutions.")
            self._snapshots.add(snapshot)
            return snapshot.to_resolution()
        return snapshot.to_resolution()

    def snapshot(
        self,
        resource_id: str,
        *,
        environment: str | None = None,
        trace_context: Mapping[str, Any] | None = None,
    ) -> SettingsEffectiveSnapshot:
        resource = _require_resource(self._resources, resource_id)
        published = self._versions.latest_published_for_resource(resource.id)
        resource_ref = resource.ref()
        value: JsonObject = {}
        sources: list[ConfigSource] = []
        validation = SettingsValidationResult.ok_result()
        version_id: str | None = None

        if published is None:
            validation = SettingsValidationResult(
                ok=True,
                warnings=("resource has no published version.",),
            )
        else:
            value = dict(published.payload)
            version_id = published.id
            sources.append(published.to_source(resource=resource_ref))

        value["enabled"] = resource.enabled
        sources.append(
            ConfigSource(
                source_id=f"resource:{resource.id}:state",
                source_kind="resource_state",
                resource=resource_ref,
                value={"enabled": resource.enabled, "status": resource.status.value},
            ),
        )

        applied_overrides: list[ConfigSource] = []
        normalized_environment = _optional_text(environment)
        if normalized_environment is not None:
            for override in self._overrides.list_for_resource(
                resource.id,
                environment=normalized_environment,
                enabled_only=True,
            ):
                value = _deep_merge(value, override.values)
                source = override.to_source(resource=resource_ref)
                sources.append(source)
                applied_overrides.append(source)

        return SettingsEffectiveSnapshot(
            id=f"snapshot_{uuid4().hex}",
            resource=resource_ref,
            effective_value=value,
            sources=tuple(sources),
            overrides=tuple(applied_overrides),
            environment=normalized_environment,
            version_id=version_id,
            validation=validation,
            metadata={"trace_context": dict(trace_context or {})},
        )


class SettingsQueryService:
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
        self._resources = resource_repository
        self._versions = version_repository
        self._overrides = override_repository
        self._snapshots = snapshot_repository
        self._audits = audit_repository
        self._resolver = resolver or SettingsEffectiveResolutionService(
            resource_repository=resource_repository,
            version_repository=version_repository,
            override_repository=override_repository,
            snapshot_repository=snapshot_repository,
        )

    def get_resource(self, resource_id: str) -> SettingsResource:
        return _require_resource(self._resources, resource_id)

    def list_resources(
        self,
        *,
        resource_kind: str | None = None,
        owner_module: str | None = None,
    ) -> tuple[SettingsResource, ...]:
        return self._resources.list(
            resource_kind=resource_kind,
            owner_module=owner_module,
        )

    def list_versions(self, resource_id: str) -> tuple[SettingsResourceVersion, ...]:
        _require_resource(self._resources, resource_id)
        return self._versions.list_for_resource(resource_id)

    def get_effective(
        self,
        resource_id: str,
        *,
        environment: str | None = None,
        trace_context: Mapping[str, Any] | None = None,
    ) -> ConfigResolution[Mapping[str, Any]]:
        return self._resolver.resolve(
            resource_id,
            environment=environment,
            trace_context=trace_context,
        )

    def latest_snapshot(
        self,
        resource_id: str,
        *,
        environment: str | None = None,
    ) -> SettingsEffectiveSnapshot | None:
        return self._snapshots.latest_for_resource(resource_id, environment=environment)

    def list_overrides(
        self,
        resource_id: str,
        *,
        environment: str | None = None,
    ) -> tuple[SettingsOverride, ...]:
        _require_resource(self._resources, resource_id)
        return self._overrides.list_for_resource(resource_id, environment=environment)

    def list_audits(self):
        return self._audits.list()


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
        self._resources = resource_repository
        self._versions = version_repository
        self._overrides = override_repository
        self._snapshots = snapshot_repository
        self._audits = audit_repository
        self._resolver = resolver or SettingsEffectiveResolutionService(
            resource_repository=resource_repository,
            version_repository=version_repository,
            override_repository=override_repository,
            snapshot_repository=snapshot_repository,
        )

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
            self._audits.mark_failed(audit.id, error={"validation": validation.to_payload()})
            return SettingsActionResult(
                status="validation_failed",
                audit=audit,
                validation=validation,
                warnings=validation.warnings,
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
        version = self._build_version(
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
            snapshot = self._publish_version_without_audit(
                resource=resource,
                version=version,
                environment=None,
                trace_context=data.trace_context,
            )
            resolution = snapshot.to_resolution()

        result_payload: JsonObject = {
            "resource": resource.to_payload(),
            "version": version.to_payload(),
            "snapshot_id": snapshot.id if snapshot is not None else None,
        }
        self._audits.mark_succeeded(audit.id, result=result_payload)
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

    def update_resource(self, data: UpdateSettingsResourceInput) -> SettingsActionResult:
        resource = _require_resource(self._resources, data.resource_id)
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
        validation = validate_settings_payload(data.payload)
        if not validation.ok:
            self._audits.mark_failed(audit.id, error={"validation": validation.to_payload()})
            return SettingsActionResult(
                status="validation_failed",
                audit=audit,
                resource=resource,
                validation=validation,
                warnings=validation.warnings,
            )

        version = self._build_version(
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
            snapshot = self._publish_version_without_audit(
                resource=resource,
                version=version,
                environment=None,
                trace_context=data.trace_context,
            )
            resolution = snapshot.to_resolution()

        self._audits.mark_succeeded(
            audit.id,
            result={
                "resource": resource.to_payload(),
                "version": version.to_payload(),
                "snapshot_id": snapshot.id if snapshot is not None else None,
            },
        )
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

    def publish_version(self, data: PublishSettingsVersionInput) -> SettingsActionResult:
        resource = _require_resource(self._resources, data.resource_id)
        audit = self._record_attempt(
            action_type="settings.version.publish",
            target_type=resource.resource_kind,
            target_id=resource.id,
            actor=data.actor,
            reason=data.reason,
            risk="configuration_change",
            request_metadata={
                "version_id": data.version_id,
                "environment": data.environment,
                "trace_context": dict(data.trace_context),
            },
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
            self._audits.mark_failed(audit.id, error={"validation": version.validation.to_payload()})
            return SettingsActionResult(
                status="validation_failed",
                audit=audit,
                resource=resource,
                version=version,
                validation=version.validation,
                warnings=version.validation.warnings,
            )

        snapshot = self._publish_version_without_audit(
            resource=resource,
            version=version,
            environment=data.environment,
            trace_context=data.trace_context,
        )
        self._audits.mark_succeeded(
            audit.id,
            result={
                "resource": resource.to_payload(),
                "version": version.to_payload(),
                "snapshot_id": snapshot.id,
            },
        )
        return SettingsActionResult(
            status="succeeded",
            audit=audit,
            resource=resource,
            version=version,
            snapshot=snapshot,
            resolution=snapshot.to_resolution(),
            validation=version.validation,
            warnings=version.validation.warnings,
        )

    def rollback_resource(self, data: RollbackSettingsResourceInput) -> SettingsActionResult:
        resource = _require_resource(self._resources, data.resource_id)
        audit = self._record_attempt(
            action_type="settings.resource.rollback",
            target_type=resource.resource_kind,
            target_id=resource.id,
            actor=data.actor,
            reason=data.reason,
            risk="configuration_rollback",
            request_metadata={
                "target_version_id": data.target_version_id,
                "environment": data.environment,
                "trace_context": dict(data.trace_context),
            },
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
            self._audits.mark_failed(audit.id, error={"validation": target.validation.to_payload()})
            return SettingsActionResult(
                status="validation_failed",
                audit=audit,
                resource=resource,
                version=target,
                validation=target.validation,
                warnings=target.validation.warnings,
            )

        snapshot = self._publish_version_without_audit(
            resource=resource,
            version=target,
            environment=data.environment,
            trace_context=data.trace_context,
        )
        self._audits.mark_succeeded(
            audit.id,
            result={
                "resource": resource.to_payload(),
                "version": target.to_payload(),
                "snapshot_id": snapshot.id,
            },
        )
        return SettingsActionResult(
            status="succeeded",
            audit=audit,
            resource=resource,
            version=target,
            snapshot=snapshot,
            resolution=snapshot.to_resolution(),
            validation=target.validation,
            warnings=target.validation.warnings,
        )

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
        resource = _require_resource(self._resources, data.resource_id)
        audit = self._record_attempt(
            action_type="settings.resource.enable" if data.enabled else "settings.resource.disable",
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
        self._audits.mark_succeeded(audit.id, result={"resource": resource.to_payload()})
        return SettingsActionResult(
            status="succeeded",
            audit=audit,
            resource=resource,
        )

    def upsert_override(self, data: UpsertSettingsOverrideInput) -> SettingsActionResult:
        resource = _require_resource(self._resources, data.resource_id)
        action_type = "settings.override.create"
        existing = self._overrides.get(data.override_id) if data.override_id is not None else None
        if existing is not None:
            action_type = "settings.override.update"
        audit = self._record_attempt(
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
            self._audits.mark_failed(audit.id, error={"validation": validation.to_payload()})
            return SettingsActionResult(
                status="validation_failed",
                audit=audit,
                resource=resource,
                validation=validation,
                warnings=validation.warnings,
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
                raise SettingsPublishError("override belongs to a different settings resource.")
            existing.update_values(data.values, reason=data.reason)
            existing.enabled = data.enabled
            existing.priority = data.priority
            self._overrides.save(existing)
            override = existing
        self._audits.mark_succeeded(audit.id, result={"override": override.to_payload()})
        return SettingsActionResult(
            status="succeeded",
            audit=audit,
            resource=resource,
            override=override,
            validation=validation,
            warnings=validation.warnings,
        )

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
        override = self._overrides.get(data.override_id)
        if override is None:
            raise SettingsNotFoundError(f"settings override '{data.override_id}' was not found.")
        resource = _require_resource(self._resources, override.resource_id)
        audit = self._record_attempt(
            action_type="settings.override.enable" if data.enabled else "settings.override.disable",
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
        self._audits.mark_succeeded(audit.id, result={"override": override.to_payload()})
        return SettingsActionResult(
            status="succeeded",
            audit=audit,
            resource=resource,
            override=override,
        )

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

    def _build_version(
        self,
        *,
        resource: SettingsResource,
        payload: Mapping[str, Any],
        actor: str | None,
        reason: str | None,
        source: str,
        validation: SettingsValidationResult,
    ) -> SettingsResourceVersion:
        version_number = _next_version_number(self._versions.list_for_resource(resource.id))
        return SettingsResourceVersion(
            id=f"{resource.id}:v{version_number}",
            resource_id=resource.id,
            resource_kind=resource.resource_kind,
            payload=dict(payload),
            version_number=version_number,
            validation=validation,
            source=source,
            reason=reason,
            created_by=actor,
        )

    def _publish_version_without_audit(
        self,
        *,
        resource: SettingsResource,
        version: SettingsResourceVersion,
        environment: str | None,
        trace_context: Mapping[str, Any],
    ) -> SettingsEffectiveSnapshot:
        for existing in self._versions.list_for_resource(resource.id):
            if existing.id != version.id:
                existing.supersede()
                self._versions.save(existing)
        version.publish()
        self._versions.save(version)
        resource.publish(version.id)
        self._resources.save(resource)
        snapshot = self._resolver.snapshot(
            resource.id,
            environment=environment,
            trace_context=trace_context,
        )
        self._snapshots.add(snapshot)
        return snapshot

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
        return self._audits.record_attempt(
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
            reason=_required_text(reason, "reason"),
            actor=actor,
            risk=risk,
            request_metadata=request_metadata or {},
        )


def _next_version_number(versions: tuple[SettingsResourceVersion, ...]) -> int:
    if not versions:
        return 1
    return max(version.version_number for version in versions) + 1


def _require_resource(
    repository: SettingsResourceRepository,
    resource_id: str,
) -> SettingsResource:
    normalized = _required_text(resource_id, "resource id")
    resource = repository.get(normalized)
    if resource is None:
        raise SettingsNotFoundError(f"settings resource '{normalized}' was not found.")
    return resource


def _required_text(value: str | None, field_name: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} is required.")
    return normalized


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _deep_merge(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> JsonObject:
    merged: JsonObject = dict(base)
    for key, value in overlay.items():
        if (
            isinstance(value, Mapping)
            and isinstance(merged.get(key), Mapping)
        ):
            merged[str(key)] = _deep_merge(merged[key], value)  # type: ignore[index]
        else:
            merged[str(key)] = value
    return merged


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): (
                "[redacted]"
                if _is_sensitive_key(str(key))
                else _redact(nested)
            )
            for key, nested in value.items()
        }
    if isinstance(value, tuple):
        return [_redact(item) for item in value]
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(
        marker in lowered
        for marker in (
            "secret",
            "token",
            "api_key",
            "apikey",
            "password",
            "value",
        )
    )
