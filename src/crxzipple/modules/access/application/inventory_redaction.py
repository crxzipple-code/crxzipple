from __future__ import annotations

from typing import Mapping

from crxzipple.modules.access.application.credential_requirement_rules import (
    canonical_credential_binding,
    is_credential_binding,
)


_SENSITIVE_METADATA_KEYS = {
    "api_key",
    "authorization",
    "password",
    "secret",
    "token",
    "value",
}


def sanitize_access_metadata(value: object) -> object:
    if isinstance(value, Mapping):
        sanitized: dict[str, object] = {}
        for key, item in value.items():
            key_string = str(key)
            if _is_sensitive_metadata_key(key_string):
                sanitized[key_string] = _masked_metadata_value(item)
            else:
                sanitized[key_string] = sanitize_access_metadata(item)
        return sanitized
    if isinstance(value, (list, tuple)):
        return [sanitize_access_metadata(item) for item in value]
    return value


def _is_sensitive_metadata_key(key: str) -> bool:
    normalized = key.strip().lower()
    return any(part in normalized for part in _SENSITIVE_METADATA_KEYS)


def _masked_metadata_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, str):
        if not value:
            return value
        if is_credential_binding(value):
            return canonical_credential_binding(value)
        return "***"
    if isinstance(value, (list, tuple)):
        return ["***" if item else item for item in value]
    if isinstance(value, Mapping):
        return {
            str(key): _masked_metadata_value(item)
            for key, item in value.items()
        }
    return "***"
