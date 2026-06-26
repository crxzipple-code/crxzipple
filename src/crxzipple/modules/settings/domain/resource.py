from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from crxzipple.modules.settings.domain.entity_common import (
    JsonObject,
    coerce_resource_status,
    normalize_optional_text,
    normalize_text,
)
from crxzipple.modules.settings.domain.value_objects import (
    SettingsResourceStatus,
    format_optional_datetime,
    normalize_datetime,
    utcnow,
)
from crxzipple.shared.domain import AggregateRoot
from crxzipple.shared.domain.events import Event
from crxzipple.shared.settings import SettingsResourceRef


@dataclass(kw_only=True)
class SettingsResource(AggregateRoot[str]):
    resource_kind: str
    owner_module: str
    scope: str = "global"
    display_name: str | None = None
    status: SettingsResourceStatus = SettingsResourceStatus.ACTIVE
    active_version_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.id = normalize_text(self.id, field_name="resource id")
        self.resource_kind = normalize_text(
            self.resource_kind,
            field_name="resource kind",
        )
        self.owner_module = normalize_text(
            self.owner_module,
            field_name="owner module",
        )
        self.scope = normalize_text(self.scope, field_name="scope")
        self.status = coerce_resource_status(self.status)
        self.display_name = normalize_optional_text(self.display_name)
        self.active_version_id = normalize_optional_text(self.active_version_id)
        self.created_at = normalize_datetime(self.created_at)
        self.updated_at = (
            normalize_datetime(self.updated_at) if self.updated_at is not None else None
        )

    @property
    def enabled(self) -> bool:
        return self.status is SettingsResourceStatus.ACTIVE

    def ref(self) -> SettingsResourceRef:
        return SettingsResourceRef(
            resource_id=self.id,
            resource_kind=self.resource_kind,
            owner_module=self.owner_module,
            scope=self.scope,
            display_name=self.display_name,
            metadata=self.metadata,
        )

    def enable(self) -> bool:
        if self.status is SettingsResourceStatus.ACTIVE:
            return False
        self.status = SettingsResourceStatus.ACTIVE
        self.updated_at = utcnow()
        self.record_event(
            Event(
                name="settings.resource_enabled",
                payload={"resource_id": self.id, "resource_kind": self.resource_kind},
            ),
        )
        return True

    def disable(self) -> bool:
        if self.status is SettingsResourceStatus.DISABLED:
            return False
        self.status = SettingsResourceStatus.DISABLED
        self.updated_at = utcnow()
        self.record_event(
            Event(
                name="settings.resource_disabled",
                payload={"resource_id": self.id, "resource_kind": self.resource_kind},
            ),
        )
        return True

    def publish(self, version_id: str) -> None:
        self.active_version_id = normalize_text(version_id, field_name="version id")
        self.updated_at = utcnow()
        self.record_event(
            Event(
                name="settings.resource_published",
                payload={
                    "resource_id": self.id,
                    "resource_kind": self.resource_kind,
                    "version_id": self.active_version_id,
                },
            ),
        )

    def to_payload(self) -> JsonObject:
        return {
            "id": self.id,
            "resource_kind": self.resource_kind,
            "owner_module": self.owner_module,
            "scope": self.scope,
            "display_name": self.display_name,
            "status": self.status.value,
            "enabled": self.enabled,
            "active_version_id": self.active_version_id,
            "metadata": dict(self.metadata),
            "created_at": format_optional_datetime(self.created_at),
            "updated_at": format_optional_datetime(self.updated_at),
        }
