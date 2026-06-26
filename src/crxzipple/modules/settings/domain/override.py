from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from crxzipple.modules.settings.domain.entity_common import (
    JsonObject,
    normalize_optional_text,
    normalize_text,
)
from crxzipple.modules.settings.domain.value_objects import (
    format_optional_datetime,
    normalize_datetime,
    utcnow,
)
from crxzipple.shared.domain import AggregateRoot
from crxzipple.shared.settings import ConfigSource, SettingsResourceRef


@dataclass(kw_only=True)
class SettingsOverride(AggregateRoot[str]):
    resource_id: str
    resource_kind: str
    environment: str
    values: Mapping[str, Any]
    enabled: bool = True
    priority: int = 100
    reason: str | None = None
    created_by: str | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = normalize_text(self.id, field_name="override id")
        self.resource_id = normalize_text(self.resource_id, field_name="resource id")
        self.resource_kind = normalize_text(
            self.resource_kind,
            field_name="resource kind",
        )
        self.environment = normalize_text(self.environment, field_name="environment")
        self.values = dict(self.values)
        self.reason = normalize_optional_text(self.reason)
        self.created_by = normalize_optional_text(self.created_by)
        self.created_at = normalize_datetime(self.created_at)
        self.updated_at = (
            normalize_datetime(self.updated_at) if self.updated_at is not None else None
        )

    def enable(self) -> bool:
        if self.enabled:
            return False
        self.enabled = True
        self.updated_at = utcnow()
        return True

    def disable(self) -> bool:
        if not self.enabled:
            return False
        self.enabled = False
        self.updated_at = utcnow()
        return True

    def update_values(
        self,
        values: Mapping[str, Any],
        *,
        reason: str | None = None,
    ) -> None:
        self.values = dict(values)
        self.reason = normalize_optional_text(reason) or self.reason
        self.updated_at = utcnow()

    def to_source(self, *, resource: SettingsResourceRef) -> ConfigSource:
        return ConfigSource(
            source_id=f"override:{self.id}",
            source_kind="environment_override",
            resource=resource,
            override_id=self.id,
            priority=self.priority,
            applied=self.enabled,
            reason=self.reason,
            value=dict(self.values),
            metadata={
                "environment": self.environment,
            },
        )

    def to_payload(self) -> JsonObject:
        return {
            "id": self.id,
            "resource_id": self.resource_id,
            "resource_kind": self.resource_kind,
            "environment": self.environment,
            "values": dict(self.values),
            "enabled": self.enabled,
            "priority": self.priority,
            "reason": self.reason,
            "created_by": self.created_by,
            "created_at": format_optional_datetime(self.created_at),
            "updated_at": format_optional_datetime(self.updated_at),
            "metadata": dict(self.metadata),
        }
