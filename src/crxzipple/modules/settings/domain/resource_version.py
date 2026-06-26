from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from crxzipple.modules.settings.domain.entity_common import (
    JsonObject,
    coerce_version_status,
    normalize_optional_text,
    normalize_text,
)
from crxzipple.modules.settings.domain.exceptions import SettingsValidationError
from crxzipple.modules.settings.domain.value_objects import (
    SettingsValidationResult,
    SettingsVersionStatus,
    format_optional_datetime,
    normalize_datetime,
    utcnow,
)
from crxzipple.shared.domain import AggregateRoot
from crxzipple.shared.domain.events import Event
from crxzipple.shared.settings import ConfigSource, SettingsResourceRef


@dataclass(kw_only=True)
class SettingsResourceVersion(AggregateRoot[str]):
    resource_id: str
    resource_kind: str
    payload: Mapping[str, Any]
    version_number: int
    status: SettingsVersionStatus = SettingsVersionStatus.DRAFT
    validation: SettingsValidationResult = field(default_factory=SettingsValidationResult)
    source: str = "manual"
    reason: str | None = None
    created_by: str | None = None
    created_at: datetime = field(default_factory=utcnow)
    published_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = normalize_text(self.id, field_name="version id")
        self.resource_id = normalize_text(self.resource_id, field_name="resource id")
        self.resource_kind = normalize_text(
            self.resource_kind,
            field_name="resource kind",
        )
        if self.version_number <= 0:
            raise SettingsValidationError("version_number must be positive.")
        self.payload = dict(self.payload)
        self.status = coerce_version_status(self.status)
        self.source = normalize_text(self.source, field_name="source")
        self.reason = normalize_optional_text(self.reason)
        self.created_by = normalize_optional_text(self.created_by)
        self.created_at = normalize_datetime(self.created_at)
        self.published_at = (
            normalize_datetime(self.published_at)
            if self.published_at is not None
            else None
        )

    def publish(self) -> None:
        if not self.validation.ok:
            self.status = SettingsVersionStatus.FAILED_VALIDATION
            raise SettingsValidationError(
                "cannot publish a version with validation errors.",
            )
        self.status = SettingsVersionStatus.PUBLISHED
        self.published_at = utcnow()
        self.record_event(
            Event(
                name="settings.version_published",
                payload={
                    "resource_id": self.resource_id,
                    "resource_kind": self.resource_kind,
                    "version_id": self.id,
                },
            ),
        )

    def supersede(self) -> None:
        if self.status is SettingsVersionStatus.PUBLISHED:
            self.status = SettingsVersionStatus.SUPERSEDED

    def to_source(self, *, resource: SettingsResourceRef) -> ConfigSource:
        return ConfigSource(
            source_id=f"version:{self.id}",
            source_kind="published_version",
            resource=resource,
            version_id=self.id,
            value=dict(self.payload),
            metadata={
                "version_number": self.version_number,
                "source": self.source,
                "reason": self.reason,
            },
        )

    def to_payload(self) -> JsonObject:
        return {
            "id": self.id,
            "resource_id": self.resource_id,
            "resource_kind": self.resource_kind,
            "payload": dict(self.payload),
            "version_number": self.version_number,
            "status": self.status.value,
            "validation": self.validation.to_payload(),
            "source": self.source,
            "reason": self.reason,
            "created_by": self.created_by,
            "created_at": format_optional_datetime(self.created_at),
            "published_at": format_optional_datetime(self.published_at),
            "metadata": dict(self.metadata),
        }
