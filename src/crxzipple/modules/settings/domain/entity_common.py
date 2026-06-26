from __future__ import annotations

from typing import Any

from crxzipple.modules.settings.domain.exceptions import SettingsValidationError
from crxzipple.modules.settings.domain.value_objects import (
    SettingsActionStatus,
    SettingsResourceStatus,
    SettingsVersionStatus,
)


JsonObject = dict[str, Any]


def normalize_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise SettingsValidationError(f"{field_name} is required.")
    return normalized


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def coerce_resource_status(
    value: SettingsResourceStatus | str,
) -> SettingsResourceStatus:
    if isinstance(value, SettingsResourceStatus):
        return value
    try:
        return SettingsResourceStatus(str(value))
    except ValueError as exc:
        raise SettingsValidationError(
            f"invalid settings resource status '{value}'.",
        ) from exc


def coerce_version_status(
    value: SettingsVersionStatus | str,
) -> SettingsVersionStatus:
    if isinstance(value, SettingsVersionStatus):
        return value
    try:
        return SettingsVersionStatus(str(value))
    except ValueError as exc:
        raise SettingsValidationError(
            f"invalid settings version status '{value}'.",
        ) from exc


def coerce_action_status(
    value: SettingsActionStatus | str,
) -> SettingsActionStatus:
    if isinstance(value, SettingsActionStatus):
        return value
    try:
        return SettingsActionStatus(str(value))
    except ValueError as exc:
        raise SettingsValidationError(
            f"invalid settings action status '{value}'.",
        ) from exc
