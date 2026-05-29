from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import re
from typing import Any, Iterator, Mapping
from urllib.parse import urlsplit, urlunsplit

from crxzipple.modules.browser.domain import BrowserValidationError


BrowserCdpSessionMode = str

_TARGET_LOST_MARKERS = (
    "target closed",
    "target crashed",
    "target detached",
    "session closed",
    "page closed",
    "frame was detached",
    "browser has been closed",
    "connection closed",
    "websocket is not open",
)


@dataclass(slots=True)
class BrowserCdpSessionLease:
    session: Any
    mode: BrowserCdpSessionMode
    target_id: str | None = None
    operation: str | None = None
    detached: bool = False

    def send(self, method: str, params: Mapping[str, Any] | None = None) -> Any:
        return BrowserCdpSessionBroker().send_command(
            self,
            method,
            params,
        )

    def detach(self) -> None:
        BrowserCdpSessionBroker().detach(self)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.session, name)


class BrowserCdpSessionBroker:
    """Creates page-scoped CDP sessions with explicit command/subscription modes."""

    def open_command_session(
        self,
        page: Any,
        *,
        operation: str | None = None,
    ) -> BrowserCdpSessionLease:
        return self.open_page_session(page, mode="command", operation=operation)

    def open_subscription_session(
        self,
        page: Any,
        *,
        operation: str | None = None,
    ) -> BrowserCdpSessionLease:
        return self.open_page_session(page, mode="subscription", operation=operation)

    def open_page_session(
        self,
        page: Any,
        *,
        mode: BrowserCdpSessionMode = "command",
        operation: str | None = None,
    ) -> BrowserCdpSessionLease:
        page_context = _page_context(page)
        new_session = getattr(page_context, "new_cdp_session", None)
        if not callable(new_session):
            raise BrowserValidationError(
                "Browser CDP session is unavailable: Playwright browser context does not support new_cdp_session().",
            )
        try:
            session = new_session(page)
        except BrowserValidationError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise BrowserValidationError(
                display_safe_cdp_error(exc, operation=operation or "open session"),
            ) from exc
        return BrowserCdpSessionLease(
            session=session,
            mode=mode,
            target_id=_page_target_id(page),
            operation=operation,
        )

    @contextmanager
    def command_session(
        self,
        page: Any,
        *,
        operation: str | None = None,
    ) -> Iterator[BrowserCdpSessionLease]:
        lease = self.open_command_session(page, operation=operation)
        try:
            yield lease
        finally:
            self.detach(lease)

    def send_command(
        self,
        session_or_lease: Any,
        method: str,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        session = _raw_session(session_or_lease)
        send = getattr(session, "send", None)
        if not callable(send):
            raise BrowserValidationError(
                "Browser CDP command failed: session does not support send().",
            )
        try:
            return send(method, dict(params or {}))
        except TypeError:
            try:
                return send(method)
            except BrowserValidationError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise BrowserValidationError(
                    display_safe_cdp_error(exc, operation=method),
                ) from exc
        except BrowserValidationError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise BrowserValidationError(
                display_safe_cdp_error(exc, operation=method),
            ) from exc

    def detach(self, session_or_lease: Any) -> None:
        session = _raw_session(session_or_lease)
        detach = getattr(session, "detach", None)
        if callable(detach):
            try:
                detach()
            except Exception:  # noqa: BLE001
                pass
        if isinstance(session_or_lease, BrowserCdpSessionLease):
            session_or_lease.detached = True


def display_safe_cdp_error(exc: Exception, *, operation: str | None = None) -> str:
    operation_label = str(operation or "operation").strip() or "operation"
    message = _sanitize_exception_message(exc)
    normalized = message.lower()
    if any(marker in normalized for marker in _TARGET_LOST_MARKERS):
        return (
            f"Browser target is no longer available during CDP {operation_label}. "
            "Next: reconcile the browser context lease or select a live tab, then retry."
        )
    if "timeout" in normalized or "timed out" in normalized:
        return (
            f"Browser CDP {operation_label} timed out. "
            "Next: retry after the page settles or select a live tab."
        )
    if "connect" in normalized or "websocket" in normalized:
        return (
            f"Browser CDP connection failed during {operation_label}. "
            "Next: verify the profile CDP endpoint and retry."
        )
    return f"Browser CDP {operation_label} failed: {message}"


def _page_context(page: Any) -> Any:
    page_context = getattr(page, "context", None)
    if callable(page_context):
        page_context = page_context()
    if page_context is None:
        page_context = getattr(page, "browser_context", None)
    if page_context is None:
        raise BrowserValidationError(
            "Browser CDP session is unavailable: Playwright page does not expose a browser context.",
        )
    return page_context


def _page_target_id(page: Any) -> str | None:
    target_id = getattr(page, "target_id", None)
    if isinstance(target_id, str) and target_id.strip():
        return target_id.strip()
    return None


def _raw_session(session_or_lease: Any) -> Any:
    if isinstance(session_or_lease, BrowserCdpSessionLease):
        return session_or_lease.session
    return session_or_lease


def _sanitize_exception_message(exc: Exception) -> str:
    message = " ".join(str(exc).split())
    if not message:
        message = exc.__class__.__name__
    message = _redact_urls(message)
    if len(message) > 600:
        message = f"{message[:597].rstrip()}..."
    return message


def _redact_urls(message: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        raw_url = match.group(0)
        try:
            parsed = urlsplit(raw_url)
        except ValueError:
            return raw_url
        if parsed.query or parsed.fragment:
            return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "[redacted]", ""))
        return raw_url

    return re.sub(r"https?://[^\s'\"<>]+", _replace, message)


__all__ = [
    "BrowserCdpSessionBroker",
    "BrowserCdpSessionLease",
    "display_safe_cdp_error",
]
