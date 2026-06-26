from __future__ import annotations

import hashlib
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def database_url_summary(value: object) -> dict[str, Any]:
    raw_value = str(value or "").strip()
    if not raw_value:
        return {
            "configured": False,
            "driver": None,
            "host": None,
            "port": None,
            "database": None,
            "username_present": False,
            "password_present": False,
            "query_keys": [],
            "redacted_url": None,
            "fingerprint": None,
        }

    try:
        parts = urlsplit(raw_value)
    except ValueError:
        return {
            "configured": True,
            "driver": None,
            "host": None,
            "port": None,
            "database": None,
            "username_present": False,
            "password_present": False,
            "query_keys": [],
            "redacted_url": "***",
            "fingerprint": settings_fingerprint(raw_value),
            "parse_status": "invalid",
        }

    return {
        "configured": True,
        "driver": parts.scheme or None,
        "host": parts.hostname,
        "port": url_port(parts),
        "database": database_name_from_url_path(parts.path),
        "username_present": bool(url_username(parts)),
        "password_present": url_password_present(parts),
        "query_keys": url_query_keys(parts.query),
        "redacted_url": redacted_database_url(parts),
        "fingerprint": settings_fingerprint(raw_value),
    }


def settings_fingerprint(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"sha256:{digest[:16]}"


def database_name_from_url_path(path: str) -> str | None:
    database = path.lstrip("/")
    return database or None


def url_username(parts: Any) -> str | None:
    try:
        return parts.username
    except ValueError:
        return None


def url_password_present(parts: Any) -> bool:
    try:
        return parts.password is not None
    except ValueError:
        return False


def url_port(parts: Any) -> int | None:
    try:
        return parts.port
    except ValueError:
        return None


def url_host_port(parts: Any) -> str | None:
    host = parts.hostname
    if not host:
        return None
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = url_port(parts)
    if port is None:
        return host
    return f"{host}:{port}"


def url_query_keys(query: str) -> list[str]:
    return sorted(
        {
            key
            for key, _value in parse_qsl(query, keep_blank_values=True)
            if key
        },
    )


def redacted_database_url(parts: Any) -> str:
    if not parts.scheme:
        return "***"
    host_port = url_host_port(parts)
    username_present = bool(url_username(parts))
    password_present = url_password_present(parts)
    if host_port is None:
        netloc = ""
    elif password_present:
        netloc = f"<user>:***@{host_port}" if username_present else f"***@{host_port}"
    elif username_present:
        netloc = f"<user>@{host_port}"
    else:
        netloc = host_port
    redacted_query = urlencode(
        [(key, "***") for key in url_query_keys(parts.query)],
        safe="*",
    )
    return urlunsplit(
        (
            parts.scheme,
            netloc,
            parts.path,
            redacted_query,
            "",
        ),
    )
