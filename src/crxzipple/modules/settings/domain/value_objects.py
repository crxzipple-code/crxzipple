from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc


JsonObject = dict[str, Any]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} is required.")
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_text_tuple(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            item.strip()
            for item in values
            if isinstance(item, str) and item.strip()
        ),
    )


class SettingsResourceStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    ARCHIVED = "archived"


class SettingsVersionStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"
    FAILED_VALIDATION = "failed_validation"


class SettingsActionStatus(StrEnum):
    ATTEMPTED = "attempted"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SettingsValidationResult:
    ok: bool = True
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "errors", _normalize_text_tuple(self.errors))
        object.__setattr__(self, "warnings", _normalize_text_tuple(self.warnings))
        if self.errors and self.ok:
            object.__setattr__(self, "ok", False)

    @classmethod
    def ok_result(cls, *, warnings: tuple[str, ...] = ()) -> "SettingsValidationResult":
        return cls(ok=True, warnings=warnings)

    @classmethod
    def failed(cls, *errors: str) -> "SettingsValidationResult":
        return cls(ok=False, errors=tuple(errors))

    def to_payload(self) -> JsonObject:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "SettingsValidationResult":
        return cls(
            ok=bool(payload.get("ok", True)),
            errors=tuple(
                str(item)
                for item in payload.get("errors", ())
                if isinstance(item, str) and item.strip()
            ),
            warnings=tuple(
                str(item)
                for item in payload.get("warnings", ())
                if isinstance(item, str) and item.strip()
            ),
            metadata=dict(payload.get("metadata") or {}),
        )


def validate_settings_payload(payload: Mapping[str, Any]) -> SettingsValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(payload, Mapping):
        errors.append("payload must be a mapping.")
        return SettingsValidationResult(ok=False, errors=tuple(errors))

    if "enabled" in payload and not isinstance(payload["enabled"], bool):
        errors.append("enabled must be a boolean when provided.")

    for key, value in payload.items():
        if not isinstance(key, str) or not key.strip():
            errors.append("payload keys must be non-empty strings.")
            continue
        lowered = key.strip().lower()
        if _looks_sensitive_key(lowered):
            warnings.append(f"{key} may contain sensitive material and should be stored as a binding ref.")
        if value is None:
            continue
        if _looks_positive_number_key(lowered):
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                errors.append(f"{key} must be numeric when provided.")
                continue
            if numeric <= 0:
                errors.append(f"{key} must be positive when provided.")

    return SettingsValidationResult(
        ok=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def format_optional_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return format_datetime_utc(value)


def normalize_datetime(value: datetime) -> datetime:
    return coerce_utc_datetime(value)


def _looks_positive_number_key(key: str) -> bool:
    return key.endswith(
        (
            "_seconds",
            "_tokens",
            "_limit",
            "_count",
            "_concurrency",
            "_attempts",
        ),
    ) or key in {"timeout", "timeout_seconds", "max_concurrency"}


def _looks_sensitive_key(key: str) -> bool:
    return any(
        marker in key
        for marker in (
            "secret",
            "token",
            "api_key",
            "apikey",
            "password",
        )
    )
