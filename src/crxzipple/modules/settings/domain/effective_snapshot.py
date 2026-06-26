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
    SettingsValidationResult,
    format_optional_datetime,
    normalize_datetime,
    utcnow,
)
from crxzipple.shared.domain import AggregateRoot
from crxzipple.shared.settings import (
    ConfigResolution,
    ConfigSource,
    SettingsResourceRef,
)


@dataclass(kw_only=True)
class SettingsEffectiveSnapshot(AggregateRoot[str]):
    resource: SettingsResourceRef
    effective_value: Mapping[str, Any]
    sources: tuple[ConfigSource, ...] = field(default_factory=tuple)
    overrides: tuple[ConfigSource, ...] = field(default_factory=tuple)
    environment: str | None = None
    version_id: str | None = None
    validation: SettingsValidationResult = field(default_factory=SettingsValidationResult)
    created_at: datetime = field(default_factory=utcnow)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = normalize_text(self.id, field_name="snapshot id")
        self.effective_value = dict(self.effective_value)
        self.sources = tuple(self.sources)
        self.overrides = tuple(self.overrides)
        self.environment = normalize_optional_text(self.environment)
        self.version_id = normalize_optional_text(self.version_id)
        self.created_at = normalize_datetime(self.created_at)

    def to_resolution(self) -> ConfigResolution[Mapping[str, Any]]:
        return ConfigResolution(
            resource=self.resource,
            effective_value=dict(self.effective_value),
            sources=self.sources,
            overrides=self.overrides,
            snapshot_id=self.id,
            resolved_at=format_optional_datetime(self.created_at),
            validation=self.validation.to_payload(),
            trace_context=dict(self.metadata.get("trace_context") or {}),
        )

    def to_payload(self) -> JsonObject:
        return {
            "id": self.id,
            "resource": self.resource.to_payload(),
            "effective_value": dict(self.effective_value),
            "sources": [source.to_payload() for source in self.sources],
            "overrides": [source.to_payload() for source in self.overrides],
            "environment": self.environment,
            "version_id": self.version_id,
            "validation": self.validation.to_payload(),
            "created_at": format_optional_datetime(self.created_at),
            "metadata": dict(self.metadata),
        }
