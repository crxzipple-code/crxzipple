from __future__ import annotations

from datetime import datetime
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc

MAX_PAYLOAD_DEPTH = 4
MAX_PAYLOAD_ITEMS = 24
MAX_TEXT_LENGTH = 512
REDACTED_VALUE = "***"

_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "credential",
    "private_key",
    "privatekey",
)
_DATABASE_URL_KEY_PARTS = ("database_url", "databaseurl")
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(\b(?:api[_-]?key|token|secret|password|credential|private[_-]?key|pwd|pass)\s*=\s*)"
    r"([^&;\s]+)",
    re.IGNORECASE,
)


def sanitize_payload(value: Any, *, depth: int = 0, key: str | None = None) -> Any:
    if depth >= MAX_PAYLOAD_DEPTH:
        return truncate(redact_sensitive_payload(value, key=key))
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return truncate(redact_sensitive_string(value, key=key))
    if isinstance(value, datetime):
        return format_datetime_utc(value)
    if isinstance(value, dict):
        items = list(value.items())[:MAX_PAYLOAD_ITEMS]
        payload: dict[str, Any] = {}
        for item_key, item_value in items:
            if not isinstance(item_key, str) or not item_key.strip():
                continue
            if is_sensitive_key(item_key) and not is_safe_numeric_token_count_key(
                item_key,
                item_value,
            ):
                payload[str(item_key)] = REDACTED_VALUE
            else:
                payload[str(item_key)] = sanitize_payload(
                    item_value,
                    depth=depth + 1,
                    key=str(item_key),
                )
        return payload
    if isinstance(value, (list, tuple, set)):
        return [
            sanitize_payload(item, depth=depth + 1, key=key)
            for item in list(value)[:MAX_PAYLOAD_ITEMS]
        ]
    return truncate(redact_sensitive_payload(value, key=key))


def redact_sensitive_payload(value: Any, *, key: str | None = None) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return redact_sensitive_string(value, key=key)
    if isinstance(value, datetime):
        return format_datetime_utc(value)
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for item_key, item_value in value.items():
            key_text = str(item_key)
            if is_sensitive_key(key_text) and not is_safe_numeric_token_count_key(
                key_text,
                item_value,
            ):
                redacted[key_text] = REDACTED_VALUE
            else:
                redacted[key_text] = redact_sensitive_payload(
                    item_value,
                    key=key_text,
                )
        return redacted
    if isinstance(value, (list, tuple, set)):
        return [redact_sensitive_payload(item, key=key) for item in value]
    return redact_sensitive_string(str(value), key=key)


def redact_sensitive_string(value: str, *, key: str | None = None) -> str:
    redacted = redact_url_password(value)
    redacted = _SENSITIVE_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}{REDACTED_VALUE}",
        redacted,
    )
    if is_database_url_key(key) and redacted == value and value:
        return REDACTED_VALUE
    return redacted


def truncate(value: Any) -> str:
    text = str(value)
    if len(text) <= MAX_TEXT_LENGTH:
        return text
    return f"{text[:MAX_TEXT_LENGTH]}..."


def is_sensitive_key(key: str) -> bool:
    normalized = normalize_sensitive_key(key)
    return any(normalize_sensitive_key(part) in normalized for part in _SENSITIVE_KEY_PARTS)


def is_safe_numeric_token_count_key(key: str, value: Any) -> bool:
    normalized = normalize_sensitive_key(key)
    return normalized.endswith("tokens") and isinstance(value, (int, float)) and not isinstance(value, bool)


def is_database_url_key(key: str | None) -> bool:
    if key is None:
        return False
    normalized = normalize_sensitive_key(key)
    return any(normalize_sensitive_key(part) in normalized for part in _DATABASE_URL_KEY_PARTS)


def normalize_sensitive_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


def redact_url_password(value: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return value
    if not parts.scheme or not parts.netloc:
        return value
    try:
        password = parts.password
    except ValueError:
        return value
    if password is None:
        return value
    safe_netloc = parts.netloc.replace(f":{password}@", ":***@", 1)
    return urlunsplit(
        (
            parts.scheme,
            safe_netloc,
            parts.path,
            parts.query,
            parts.fragment,
        ),
    )


def optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def int_value(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(float(value))
        except ValueError:
            return 0
    return 0


def optional_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


def count_map(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): int_value(item)
        for key, item in value.items()
        if isinstance(key, str) and key.strip()
    }


def parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return coerce_utc_datetime(datetime.fromisoformat(value))
    except ValueError:
        return None
