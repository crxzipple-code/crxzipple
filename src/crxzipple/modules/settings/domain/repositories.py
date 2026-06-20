from __future__ import annotations

from typing import Any, Protocol

from crxzipple.modules.settings.domain.entities import (
    SettingsActionAudit,
    SettingsEffectiveSnapshot,
    SettingsOverride,
    SettingsResource,
    SettingsResourceVersion,
)


class SettingsResourceRepository(Protocol):
    def add(self, resource: SettingsResource) -> None: ...

    def save(self, resource: SettingsResource) -> None: ...

    def get(self, resource_id: str) -> SettingsResource | None: ...

    def list(
        self,
        *,
        resource_kind: str | None = None,
        owner_module: str | None = None,
    ) -> tuple[SettingsResource, ...]: ...


class SettingsResourceVersionRepository(Protocol):
    def add(self, version: SettingsResourceVersion) -> None: ...

    def save(self, version: SettingsResourceVersion) -> None: ...

    def get(self, version_id: str) -> SettingsResourceVersion | None: ...

    def list_for_resource(self, resource_id: str) -> tuple[SettingsResourceVersion, ...]: ...

    def latest_for_resource(self, resource_id: str) -> SettingsResourceVersion | None: ...

    def latest_published_for_resource(
        self,
        resource_id: str,
    ) -> SettingsResourceVersion | None: ...

    def latest_published_for_resources(
        self,
        resource_ids: tuple[str, ...],
    ) -> dict[str, SettingsResourceVersion]: ...


class SettingsOverrideRepository(Protocol):
    def add(self, override: SettingsOverride) -> None: ...

    def save(self, override: SettingsOverride) -> None: ...

    def get(self, override_id: str) -> SettingsOverride | None: ...

    def list_for_resource(
        self,
        resource_id: str,
        *,
        environment: str | None = None,
        enabled_only: bool = False,
    ) -> tuple[SettingsOverride, ...]: ...

    def list_for_resources(
        self,
        resource_ids: tuple[str, ...],
        *,
        environment: str | None = None,
        enabled_only: bool = False,
    ) -> dict[str, tuple[SettingsOverride, ...]]: ...


class SettingsEffectiveSnapshotRepository(Protocol):
    def add(self, snapshot: SettingsEffectiveSnapshot) -> None: ...

    def get(self, snapshot_id: str) -> SettingsEffectiveSnapshot | None: ...

    def latest_for_resource(
        self,
        resource_id: str,
        *,
        environment: str | None = None,
    ) -> SettingsEffectiveSnapshot | None: ...


class SettingsActionAuditRepository(Protocol):
    def record_attempt(
        self,
        *,
        action_type: str,
        target_type: str,
        target_id: str | None,
        reason: str,
        actor: str | None = None,
        risk: str | None = None,
        request_metadata: dict[str, Any] | None = None,
    ) -> SettingsActionAudit: ...

    def mark_succeeded(
        self,
        audit_id: str,
        *,
        result: dict[str, Any] | None = None,
    ) -> SettingsActionAudit: ...

    def mark_failed(
        self,
        audit_id: str,
        *,
        error: dict[str, Any],
    ) -> SettingsActionAudit: ...

    def get(self, audit_id: str) -> SettingsActionAudit | None: ...

    def list(self) -> tuple[SettingsActionAudit, ...]: ...
