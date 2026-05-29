from __future__ import annotations

from typing import Iterable
from urllib.parse import quote, urlsplit, urlunsplit

from crxzipple.modules.browser.domain import BrowserValidationError

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def normalize_cdp_http_base(value: str | None) -> str:
    normalized = value.strip().rstrip("/") if isinstance(value, str) else ""
    if not normalized:
        raise BrowserValidationError("Resolved browser profile does not define a CDP URL.")
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise BrowserValidationError(
            f"Resolved browser profile exposes an invalid CDP URL '{normalized}'.",
        )
    return normalized


def append_cdp_path(base_url: str, path: str) -> str:
    normalized_base = normalize_cdp_http_base(base_url)
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{normalized_base}{normalized_path}"


def build_cdp_json_new_endpoint(base_url: str, target_url: str) -> str:
    encoded_target = quote(target_url, safe=":/%")
    return f"{append_cdp_path(base_url, '/json/new')}?{encoded_target}"


def browser_ref_to_cdp_http_base(browser_ref: str | None) -> str | None:
    normalized = browser_ref.strip() if isinstance(browser_ref, str) else ""
    if not normalized:
        return None
    parsed = urlsplit(normalized)
    if not parsed.scheme or not parsed.netloc:
        return None
    if parsed.scheme == "ws":
        scheme = "http"
    elif parsed.scheme == "wss":
        scheme = "https"
    else:
        return None
    return f"{scheme}://{parsed.netloc}"


def normalize_cdp_ws_url(raw_ws_url: str | None, cdp_base_url: str | None) -> str | None:
    normalized_raw = raw_ws_url.strip() if isinstance(raw_ws_url, str) else ""
    if not normalized_raw:
        return None
    if cdp_base_url is None:
        return normalized_raw
    parsed_ws = urlsplit(normalized_raw)
    if parsed_ws.scheme not in {"ws", "wss"} or not parsed_ws.netloc:
        return normalized_raw
    parsed_base = urlsplit(normalize_cdp_http_base(cdp_base_url))
    ws_scheme = "wss" if parsed_base.scheme == "https" else "ws"
    return urlunsplit(
        (
            ws_scheme,
            parsed_base.netloc,
            parsed_ws.path,
            parsed_ws.query,
            parsed_ws.fragment,
        )
    )


def candidate_cdp_http_bases(
    base_url: str | None,
    *,
    cached_base_url: str | None = None,
    browser_ref: str | None = None,
) -> tuple[str, ...]:
    candidates: list[str] = []

    def _push(value: str | None) -> None:
        normalized = value.strip().rstrip("/") if isinstance(value, str) else ""
        if normalized and normalized not in candidates:
            candidates.append(normalized)

    _push(cached_base_url)
    _push(browser_ref_to_cdp_http_base(browser_ref))
    normalized_base = None
    if isinstance(base_url, str) and base_url.strip():
        normalized_base = normalize_cdp_http_base(base_url)
        _push(normalized_base)

    if normalized_base is None:
        return tuple(candidates)
    parsed = urlsplit(normalized_base)
    host = parsed.hostname or ""
    port = parsed.port
    if port is not None and host in _LOOPBACK_HOSTS:
        _push(f"{parsed.scheme}://localhost:{port}")
        _push(f"{parsed.scheme}://127.0.0.1:{port}")
    return tuple(candidates)


def json_tab_endpoints(base_url: str, target_id: str) -> dict[str, str]:
    return {
        "version": append_cdp_path(base_url, "/json/version"),
        "list": append_cdp_path(base_url, "/json/list"),
        "new": append_cdp_path(base_url, "/json/new"),
        "activate": append_cdp_path(base_url, f"/json/activate/{target_id}"),
        "close": append_cdp_path(base_url, f"/json/close/{target_id}"),
    }


def first_cdp_http_base(values: Iterable[str | None]) -> str | None:
    for value in values:
        normalized = value.strip().rstrip("/") if isinstance(value, str) else ""
        if normalized:
            return normalized
    return None
