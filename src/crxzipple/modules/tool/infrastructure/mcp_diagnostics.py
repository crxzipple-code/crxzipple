from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

REDACTED_DIAGNOSTIC_VALUE = "redacted"

_URL_RE = re.compile(r"(?P<url>[a-zA-Z][a-zA-Z0-9+.-]*://[^\s,;]+)")
_AUTHORIZATION_BEARER_RE = re.compile(
    r"(\bauthorization\s*[:=]\s*Bearer\s+)([^\s,;&]+)",
    re.IGNORECASE,
)
_BEARER_RE = re.compile(r"(\bBearer\s+)([^\s,;&]+)", re.IGNORECASE)
_SENSITIVE_JSON_FIELD_RE = re.compile(
    r"(?P<prefix>(?P<quote>['\"])(?:api[_-]?key|access[_-]?token|"
    r"refresh[_-]?token|id[_-]?token|bearer[_-]?token|token|secret|"
    r"password|credential|private[_-]?key|pwd|pass)(?P=quote)\s*:\s*"
    r"(?P<value_quote>['\"]))(?:.*?)(?P=value_quote)",
    re.IGNORECASE,
)
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|id[_-]?token|"
    r"bearer[_-]?token|token|secret|password|credential|private[_-]?key|"
    r"pwd|pass)\b\s*[:=]\s*['\"]?)([^'\"\s,;&#]+)",
    re.IGNORECASE,
)
_SENSITIVE_QUERY_KEYS = {
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "id_token",
    "bearer_token",
    "token",
    "secret",
    "password",
    "credential",
    "private_key",
    "privatekey",
    "pwd",
    "pass",
}


def redact_mcp_diagnostic(value: object) -> str:
    text = str(value)
    redacted = _URL_RE.sub(
        lambda match: _redact_url_candidate(match.group("url")),
        text,
    )
    redacted = _AUTHORIZATION_BEARER_RE.sub(
        lambda match: f"{match.group(1)}{REDACTED_DIAGNOSTIC_VALUE}",
        redacted,
    )
    redacted = _BEARER_RE.sub(
        lambda match: f"{match.group(1)}{REDACTED_DIAGNOSTIC_VALUE}",
        redacted,
    )
    redacted = _SENSITIVE_JSON_FIELD_RE.sub(
        lambda match: (
            f"{match.group('prefix')}{REDACTED_DIAGNOSTIC_VALUE}"
            f"{match.group('value_quote')}"
        ),
        redacted,
    )
    return _SENSITIVE_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}{REDACTED_DIAGNOSTIC_VALUE}",
        redacted,
    )


def redact_mcp_command(command: object) -> str:
    if isinstance(command, (list, tuple)):
        return redact_mcp_diagnostic(" ".join(str(item) for item in command))
    return redact_mcp_diagnostic(command)


def _redact_url_candidate(value: str) -> str:
    trailing = ""
    while value and value[-1] in ".)]}'\"":
        trailing = value[-1] + trailing
        value = value[:-1]

    try:
        parts = urlsplit(value)
    except ValueError:
        return value + trailing
    if not parts.scheme or not parts.netloc:
        return value + trailing

    netloc = parts.netloc
    if parts.password is not None:
        host_port = parts.netloc.rsplit("@", maxsplit=1)[-1]
        username = parts.username or ""
        netloc = f"{username}:{REDACTED_DIAGNOSTIC_VALUE}@{host_port}"

    query = parts.query
    if query:
        query = _redact_url_parameter_string(query)
    fragment = parts.fragment
    if fragment:
        fragment = _redact_url_parameter_string(fragment)

    return urlunsplit(
        (
            parts.scheme,
            netloc,
            parts.path,
            query,
            fragment,
        ),
    ) + trailing


def _redact_url_parameter_string(value: str) -> str:
    if "=" not in value:
        return _SENSITIVE_ASSIGNMENT_RE.sub(
            lambda match: f"{match.group(1)}{REDACTED_DIAGNOSTIC_VALUE}",
            value,
        )
    return urlencode(
        [
            (
                key,
                REDACTED_DIAGNOSTIC_VALUE
                if _is_sensitive_query_key(key)
                else item_value,
            )
            for key, item_value in parse_qsl(value, keep_blank_values=True)
        ],
    )


def _is_sensitive_query_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    return any(
        re.sub(r"[^a-z0-9]", "", candidate) == normalized
        for candidate in _SENSITIVE_QUERY_KEYS
    )


__all__ = [
    "REDACTED_DIAGNOSTIC_VALUE",
    "redact_mcp_command",
    "redact_mcp_diagnostic",
]
