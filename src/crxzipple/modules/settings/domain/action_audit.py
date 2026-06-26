from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from crxzipple.modules.settings.domain.entity_common import (
    JsonObject,
    coerce_action_status,
    normalize_optional_text,
    normalize_text,
)
from crxzipple.modules.settings.domain.value_objects import (
    SettingsActionStatus,
    format_optional_datetime,
    normalize_datetime,
    utcnow,
)
from crxzipple.shared.domain import AggregateRoot


@dataclass(kw_only=True)
class SettingsActionAudit(AggregateRoot[str]):
    action_type: str
    target_type: str
    target_id: str | None
    reason: str
    status: SettingsActionStatus = SettingsActionStatus.ATTEMPTED
    actor: str | None = None
    risk: str | None = None
    request_metadata: Mapping[str, Any] = field(default_factory=dict)
    result: Mapping[str, Any] | None = None
    error: Mapping[str, Any] | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime | None = None
    redaction_policy: Mapping[str, Any] = field(
        default_factory=lambda: {"mode": "metadata_only"},
    )

    def __post_init__(self) -> None:
        self.id = normalize_text(self.id, field_name="audit id")
        self.action_type = normalize_text(self.action_type, field_name="action type")
        self.target_type = normalize_text(self.target_type, field_name="target type")
        self.status = coerce_action_status(self.status)
        self.target_id = normalize_optional_text(self.target_id)
        self.reason = normalize_text(self.reason, field_name="reason")
        self.actor = normalize_optional_text(self.actor)
        self.risk = normalize_optional_text(self.risk)
        self.created_at = normalize_datetime(self.created_at)
        self.updated_at = (
            normalize_datetime(self.updated_at) if self.updated_at is not None else None
        )

    def mark_succeeded(self, *, result: Mapping[str, Any] | None = None) -> None:
        self.status = SettingsActionStatus.SUCCEEDED
        self.result = dict(result or {})
        self.error = None
        self.updated_at = utcnow()

    def mark_failed(self, *, error: Mapping[str, Any]) -> None:
        self.status = SettingsActionStatus.FAILED
        self.error = dict(error)
        self.updated_at = utcnow()

    def to_payload(self) -> JsonObject:
        return {
            "id": self.id,
            "action_type": self.action_type,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "reason": self.reason,
            "status": self.status.value,
            "actor": self.actor,
            "risk": self.risk,
            "request_metadata": dict(self.request_metadata),
            "result": dict(self.result or {}) if self.result is not None else None,
            "error": dict(self.error or {}) if self.error is not None else None,
            "created_at": format_optional_datetime(self.created_at),
            "updated_at": format_optional_datetime(self.updated_at),
            "redaction_policy": dict(self.redaction_policy),
        }
