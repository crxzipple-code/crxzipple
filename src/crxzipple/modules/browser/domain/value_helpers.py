from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import urlsplit

from .exceptions import BrowserValidationError


def _normalize_ref_id(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        raise BrowserValidationError("ref is required.")
    return normalized


def _normalize_profile_name(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        raise BrowserValidationError("profile name is required.")
    return normalized


def _normalize_pool_id(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        raise BrowserValidationError("pool id is required.")
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_required_text(value: str, *, label: str) -> str:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        raise BrowserValidationError(f"{label} is required.")
    return normalized


def _ensure_aware_utc(value: datetime, *, label: str) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    normalized = value.astimezone(timezone.utc)
    if normalized.year < 2000:
        raise BrowserValidationError(f"{label} is invalid.")
    return normalized


def _normalize_profile_directory(value: str | None) -> str | None:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        return None
    if "/" in normalized or "\\" in normalized:
        raise BrowserValidationError(
            "profile_directory must be a browser profile name, not a filesystem path.",
        )
    return normalized


def _normalize_proxy_bypass_list(
    value: tuple[str, ...] | list[str] | None,
) -> tuple[str, ...]:
    if value is None:
        return ()
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        entry = str(item).strip()
        if not entry or entry in seen:
            continue
        seen.add(entry)
        normalized.append(entry)
    return tuple(normalized)


def _proxy_server_has_credentials(value: str | None) -> bool:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        return False
    parsed = urlsplit(normalized)
    return bool(parsed.username or parsed.password)


def _require_positive_port(value: int | None, *, label: str) -> int | None:
    if value is None:
        return None
    numeric = int(value)
    if numeric < 1:
        raise BrowserValidationError(f"{label} must be greater than or equal to 1.")
    return numeric


def _normalize_frame_path(value: tuple[int, ...] | list[int] | None) -> tuple[int, ...]:
    if value is None:
        return ()
    normalized: list[int] = []
    for index in value:
        numeric = int(index)
        if numeric < 0:
            raise BrowserValidationError(
                "frame_path indexes must be greater than or equal to 0."
            )
        normalized.append(numeric)
    return tuple(normalized)


def _normalize_endpoint_map(value: Mapping[str, str] | None) -> dict[str, str] | None:
    if value is None:
        return None
    normalized: dict[str, str] = {}
    for key, item in value.items():
        normalized_key = str(key).strip()
        normalized_value = str(item).strip()
        if not normalized_key or not normalized_value:
            continue
        normalized[normalized_key] = normalized_value
    return normalized or None


def _normalize_text_tuple(
    values: tuple[str, ...] | list[str] | None,
) -> tuple[str, ...]:
    if values is None:
        return ()
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        normalized.append(text)
        seen.add(text)
    return tuple(normalized)


def _normalize_numeric_mapping(
    value: Mapping[str, Any] | None,
) -> dict[str, float] | None:
    if value is None:
        return None
    normalized: dict[str, float] = {}
    for key, item in value.items():
        normalized_key = str(key).strip()
        if not normalized_key:
            continue
        try:
            normalized[normalized_key] = float(item)
        except (TypeError, ValueError) as exc:
            raise BrowserValidationError(f"{normalized_key} must be numeric.") from exc
    return normalized or None


def _normalize_confidence(value: float | int | None) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise BrowserValidationError("stored ref confidence must be numeric.") from exc
    if numeric < 0 or numeric > 1:
        raise BrowserValidationError("stored ref confidence must be between 0 and 1.")
    return numeric


def _normalize_profile_name_tuple(
    values: tuple[str, ...] | list[str] | None,
) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in _normalize_text_tuple(values):
        name = _normalize_profile_name(value)
        if name in seen:
            continue
        seen.add(name)
        normalized.append(name)
    return tuple(normalized)


def _normalize_target_hosts(
    values: tuple[str, ...] | list[str] | None,
) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in _normalize_text_tuple(values):
        host = value.lower()
        if host in seen:
            continue
        seen.add(host)
        normalized.append(host)
    return tuple(normalized)


def _require_positive_int(value: int | None, *, label: str) -> int | None:
    if value is None:
        return None
    numeric = int(value)
    if numeric < 1:
        raise BrowserValidationError(f"{label} must be greater than or equal to 1.")
    return numeric


def _require_non_negative_int(value: int, *, label: str) -> int:
    numeric = int(value)
    if numeric < 0:
        raise BrowserValidationError(f"{label} must be greater than or equal to 0.")
    return numeric


def _normalize_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    return dict(value)


def _normalize_header_mapping(value: Mapping[str, Any] | None) -> dict[str, str]:
    if value is None:
        return {}
    normalized: dict[str, str] = {}
    for key, item in value.items():
        normalized_key = str(key).strip()
        if not normalized_key:
            continue
        normalized[normalized_key] = "" if item is None else str(item)
    return normalized


def _normalize_status_code(value: int | None, *, label: str) -> int | None:
    if value is None:
        return None
    numeric = int(value)
    if numeric < 0 or numeric > 999:
        raise BrowserValidationError(f"{label} must be between 0 and 999.")
    return numeric


def _normalize_network_capture_status(value: str) -> str:
    normalized = _normalize_required_text(value, label="capture status").lower()
    if normalized not in {"active", "stopped"}:
        raise BrowserValidationError("capture status must be one of: active, stopped.")
    return normalized


def _normalize_network_body_kind(value: str) -> str:
    normalized = _normalize_required_text(value, label="body kind").lower()
    if normalized not in {"request", "response"}:
        raise BrowserValidationError("body kind must be one of: request, response.")
    return normalized


def _normalize_network_resource_type(value: str | None) -> str:
    return (_normalize_optional_text(value) or "other").lower()


def _normalize_network_method(value: str) -> str:
    return _normalize_required_text(value, label="method").upper()


def _normalize_network_filter_domain(value: str | None) -> str | None:
    normalized = _normalize_optional_text(value)
    return normalized.lower() if normalized is not None else None
