from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from enum import Enum
import re
from pathlib import Path
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

REDACTED_VALUE = "***"

_SECRET_KEY_PARTS = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "credential",
    "private_key",
    "privatekey",
)
_DATABASE_URL_KEY_PARTS = (
    "database_url",
    "databaseurl",
)
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(\b(?:api[_-]?key|token|secret|password|credential|private[_-]?key|pwd|pass)\s*=\s*)"
    r"([^&;\s]+)",
    re.IGNORECASE,
)


def redact_value(value: Any, *, _key: str | None = None) -> Any:
    plain = to_plain_payload(value)
    if isinstance(plain, dict):
        redacted: dict[str, Any] = {}
        for key, item in plain.items():
            key_text = str(key)
            if is_sensitive_key(key_text) and not is_safe_numeric_token_count_key(
                key_text,
                item,
            ):
                redacted[key] = REDACTED_VALUE
            else:
                redacted[key] = redact_value(item, _key=key_text)
        return redacted
    if isinstance(plain, list):
        return [redact_value(item, _key=_key) for item in plain]
    if isinstance(plain, str):
        return redact_string(plain, force_database_url=is_database_url_key(_key))
    return plain


def to_plain_payload(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    to_payload = getattr(value, "to_payload", None)
    if callable(to_payload):
        return to_plain_payload(to_payload())
    if is_dataclass(value):
        return to_plain_payload(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): to_plain_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_plain_payload(item) for item in value]
    return str(value)


def is_sensitive_key(key: str) -> bool:
    normalized = normalize_secret_key(key)
    return any(normalize_secret_key(part) in normalized for part in _SECRET_KEY_PARTS)


def is_safe_numeric_token_count_key(key: str, value: Any) -> bool:
    normalized = normalize_secret_key(key)
    if not normalized.endswith("tokens"):
        return False
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_database_url_key(key: str | None) -> bool:
    if key is None:
        return False
    normalized = normalize_secret_key(key)
    return any(normalize_secret_key(part) in normalized for part in _DATABASE_URL_KEY_PARTS)


def normalize_secret_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


def redact_string(value: str, *, force_database_url: bool = False) -> str:
    redacted = redact_url_password(value)
    redacted = _SENSITIVE_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}{REDACTED_VALUE}",
        redacted,
    )
    if force_database_url and redacted == value and value:
        return REDACTED_VALUE
    return redacted


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
    username = parts.username or ""
    user_info = f"{username}:{REDACTED_VALUE}@"
    return urlunsplit(
        SplitResult(
            scheme=parts.scheme,
            netloc=f"{user_info}{url_host_port(parts)}",
            path=parts.path,
            query=parts.query,
            fragment=parts.fragment,
        ),
    )


def url_host_port(parts: SplitResult) -> str:
    fallback = parts.netloc.rsplit("@", maxsplit=1)[-1]
    try:
        host = parts.hostname
        port = parts.port
    except ValueError:
        return fallback
    if host is None:
        return fallback
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if port is not None:
        return f"{host}:{port}"
    return host
