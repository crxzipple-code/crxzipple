"""Shared browser profile runtime endpoint helpers for app assembly."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit


def browser_profile_cdp_port(
    browser_system_config: Any,
    profile: Any,
    index: int,
) -> int | None:
    if getattr(profile, "cdp_port", None) is not None:
        return int(profile.cdp_port)
    cdp_url = getattr(profile, "cdp_url", None)
    if isinstance(cdp_url, str) and cdp_url.strip():
        parsed = urlsplit(cdp_url.strip())
        return parsed.port
    if getattr(profile, "driver", None) == "existing-session":
        return None
    cdp_start = getattr(browser_system_config, "cdp_port_range_start", None)
    if cdp_start is None:
        cdp_start = getattr(browser_system_config, "cdp_port", None)
    if cdp_start is None:
        return None
    return int(cdp_start) + int(index)


def browser_profile_cdp_endpoint(
    browser_system_config: Any,
    profile: Any,
    *,
    cdp_port: int | None,
) -> str | None:
    cdp_url = getattr(profile, "cdp_url", None)
    if isinstance(cdp_url, str) and cdp_url.strip():
        return cdp_url.strip()
    if cdp_port is None:
        return None
    cdp_host = str(
        getattr(browser_system_config, "cdp_host", "127.0.0.1") or "127.0.0.1",
    )
    return f"http://{cdp_host}:{cdp_port}"


__all__ = [
    "browser_profile_cdp_endpoint",
    "browser_profile_cdp_port",
]
