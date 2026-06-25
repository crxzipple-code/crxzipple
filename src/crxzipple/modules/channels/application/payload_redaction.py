from __future__ import annotations

from typing import Any


REDACTED_CHANNEL_VALUE = "[redacted]"

_SENSITIVE_EXACT_KEYS = {
    "access_token",
    "api_key",
    "app_secret",
    "authorization",
    "callback_url",
    "client_secret",
    "cookie",
    "id_token",
    "lark_app_secret",
    "lark_verification_token",
    "password",
    "refresh_token",
    "secret",
    "secret_value",
    "token",
    "value",
    "webhook_callback_url",
    "webhook_signing_secret",
}

_SENSITIVE_KEY_PARTS = (
    "authorization",
    "cookie",
    "secret",
    "token",
)


def redact_channel_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): (
                REDACTED_CHANNEL_VALUE
                if _is_sensitive_channel_key(str(key))
                else redact_channel_payload(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_channel_payload(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_channel_payload(item) for item in value)
    return value


def _is_sensitive_channel_key(key: str) -> bool:
    normalized = key.strip().lower()
    if normalized in _SENSITIVE_EXACT_KEYS:
        return True
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)
