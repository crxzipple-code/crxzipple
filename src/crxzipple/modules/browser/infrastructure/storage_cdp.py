from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

from crxzipple.modules.browser.domain import BrowserValidationError

from .cdp_sessions import BrowserCdpSessionBroker
from .storage_payloads import payload_text_any


def page_security_origin(page: Any, payload: Mapping[str, Any]) -> str:
    explicit_origin = payload_text_any(payload, "security_origin", "securityOrigin", "origin")
    if explicit_origin is not None:
        return explicit_origin
    url = str(getattr(page, "url", "") or "")
    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.netloc:
        raise BrowserValidationError(
            "Browser storage inspection requires a page URL with scheme and host.",
        )
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def new_page_cdp_session(page: Any) -> Any:
    return BrowserCdpSessionBroker().open_command_session(page)


def send_cdp_session_command(
    session: Any,
    method: str,
    params: Mapping[str, Any] | None = None,
) -> Any:
    return BrowserCdpSessionBroker().send_command(session, method, params)


def detach_cdp_session(session: Any) -> None:
    BrowserCdpSessionBroker().detach(session)


__all__ = [
    "detach_cdp_session",
    "new_page_cdp_session",
    "page_security_origin",
    "send_cdp_session_command",
]
