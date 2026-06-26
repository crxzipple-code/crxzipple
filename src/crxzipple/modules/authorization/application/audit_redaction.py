from __future__ import annotations

from typing import Any


SENSITIVE_AUDIT_KEY_FRAGMENTS = (
    "api_key",
    "authorization",
    "bearer",
    "client_secret",
    "cookie",
    "credential",
    "password",
    "refresh_token",
    "secret",
    "token",
)
REDACTED_AUDIT_VALUE = "[redacted]"


def redact_audit_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        str(key): redact_audit_value(str(key), value)
        for key, value in dict(payload).items()
    }


def redact_audit_value(key: str, value: Any) -> Any:
    if is_sensitive_audit_key(key):
        return REDACTED_AUDIT_VALUE
    if isinstance(value, dict):
        return {
            str(child_key): redact_audit_value(str(child_key), child_value)
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [redact_audit_value(key, item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_audit_value(key, item) for item in value)
    return value


def is_sensitive_audit_key(key: str) -> bool:
    normalized = key.strip().lower()
    return any(fragment in normalized for fragment in SENSITIVE_AUDIT_KEY_FRAGMENTS)


__all__ = [
    "REDACTED_AUDIT_VALUE",
    "SENSITIVE_AUDIT_KEY_FRAGMENTS",
    "is_sensitive_audit_key",
    "redact_audit_payload",
    "redact_audit_value",
]
