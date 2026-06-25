from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from crxzipple.modules.browser.domain import (
    BrowserProfileRuntimeState,
    BrowserTab,
    BrowserValidationError,
)

from .cdp_urls import json_tab_endpoints, normalize_cdp_ws_url

METADATA_TABS_KEY = "tabs"
METADATA_TABS_REFRESHED_AT_KEY = "tabs_refreshed_at"
METADATA_NEXT_TAB_ID_KEY = "next_tab_id"
METADATA_ACTIVE_TARGET_KEY = "active_target_id"
METADATA_CDP_BASE_URL_KEY = "cdp_base_url"
PAGE_TAB_TYPES = {"page"}
BACKGROUND_TAB_TYPES = {"background_page", "background"}
WORKER_TAB_TYPES = {"worker", "service_worker", "shared_worker"}
TABS_CACHE_FRESHNESS_SECONDS = 2.0


def copy_tab_payloads(runtime_state: BrowserProfileRuntimeState) -> list[dict[str, Any]]:
    raw = runtime_state.metadata.get(METADATA_TABS_KEY, [])
    if not isinstance(raw, list):
        return []
    payloads: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            payloads.append(dict(item))
    return payloads


def load_tabs(runtime_state: BrowserProfileRuntimeState) -> tuple[BrowserTab, ...]:
    return tuple(
        BrowserTab(
            target_id=str(payload.get("target_id", "")).strip(),
            url=str(payload.get("url", "")).strip(),
            title=str(payload.get("title", "")).strip(),
            type=str(payload.get("type", "page")).strip() or "page",
            ws_url=(
                str(payload["ws_url"])
                if payload.get("ws_url") is not None
                else None
            ),
            json_endpoints=(
                dict(payload["json_endpoints"])
                if isinstance(payload.get("json_endpoints"), dict)
                else None
            ),
        )
        for payload in copy_tab_payloads(runtime_state)
        if str(payload.get("target_id", "")).strip()
    )


def store_tabs(
    runtime_state: BrowserProfileRuntimeState,
    tabs: tuple[BrowserTab, ...],
) -> None:
    runtime_state.metadata[METADATA_TABS_KEY] = [
        {
            "target_id": tab.target_id,
            "url": tab.url,
            "title": tab.title,
            "type": tab.type,
            "ws_url": tab.ws_url,
            "json_endpoints": dict(tab.json_endpoints) if tab.json_endpoints else None,
        }
        for tab in tabs
    ]
    runtime_state.metadata[METADATA_TABS_REFRESHED_AT_KEY] = time.time()


def tabs_cache_is_fresh(runtime_state: BrowserProfileRuntimeState) -> bool:
    if not load_tabs(runtime_state):
        return False
    raw = runtime_state.metadata.get(METADATA_TABS_REFRESHED_AT_KEY)
    try:
        refreshed_at = float(raw)
    except (TypeError, ValueError):
        return False
    return (time.time() - refreshed_at) <= TABS_CACHE_FRESHNESS_SECONDS


def host_generation(
    *,
    base_url: str,
    browser_ref: str | None,
    running_pid: int | None,
) -> str:
    payload = {
        "base_url": str(base_url).strip(),
        "browser_ref": str(browser_ref).strip() if browser_ref else None,
        "running_pid": int(running_pid) if running_pid is not None else None,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def next_tab_id(runtime_state: BrowserProfileRuntimeState, *, prefix: str) -> str:
    current = runtime_state.metadata.get(METADATA_NEXT_TAB_ID_KEY, 1)
    try:
        numeric = int(current)
    except (TypeError, ValueError):
        numeric = 1
    runtime_state.metadata[METADATA_NEXT_TAB_ID_KEY] = numeric + 1
    return f"{prefix}-{numeric}"


def set_active_target(runtime_state: BrowserProfileRuntimeState, target_id: str | None) -> None:
    normalized = target_id.strip() if isinstance(target_id, str) else ""
    runtime_state.metadata[METADATA_ACTIVE_TARGET_KEY] = normalized or None


def find_tab(
    runtime_state: BrowserProfileRuntimeState,
    *,
    target_id: str,
) -> BrowserTab:
    for tab in load_tabs(runtime_state):
        if tab.target_id == target_id:
            return tab
    raise BrowserValidationError(f"Browser tab '{target_id}' was not found.")


def canonicalize_opened_tab(
    *,
    opened_tab: BrowserTab,
    live_tabs: tuple[BrowserTab, ...],
) -> BrowserTab:
    if not live_tabs:
        return opened_tab
    for tab in live_tabs:
        if tab.target_id == opened_tab.target_id:
            return tab
    same_ws_url = [
        tab for tab in live_tabs if tab.ws_url and opened_tab.ws_url and tab.ws_url == opened_tab.ws_url
    ]
    if len(same_ws_url) == 1:
        return same_ws_url[0]
    same_url = [
        tab
        for tab in live_tabs
        if str(tab.url or "").strip() and str(tab.url or "").strip() == str(opened_tab.url or "").strip()
    ]
    if same_url:
        return same_url[-1]
    return live_tabs[-1]


def browser_tab_type(raw_type: object) -> str:
    normalized = str(raw_type or "page").strip().lower()
    if normalized in PAGE_TAB_TYPES:
        return "page"
    if normalized in BACKGROUND_TAB_TYPES:
        return "background"
    if normalized in WORKER_TAB_TYPES:
        return "worker"
    return "other"


def tab_from_cdp_payload(
    payload: dict[str, Any],
    *,
    include_ws_url: bool,
    include_json_endpoints: bool,
    base_url: str,
) -> BrowserTab:
    target_id = str(payload.get("id", "")).strip()
    return BrowserTab(
        target_id=target_id,
        url=str(payload.get("url", "")).strip(),
        title=str(payload.get("title", "")).strip(),
        type=browser_tab_type(payload.get("type")),
        ws_url=(
            normalize_cdp_ws_url(
                str(payload.get("webSocketDebuggerUrl", "")).strip(),
                base_url,
            )
            if include_ws_url and payload.get("webSocketDebuggerUrl")
            else None
        ),
        json_endpoints=(
            json_tab_endpoints(base_url, target_id)
            if include_json_endpoints and target_id
            else None
        ),
    )


__all__ = [
    "METADATA_ACTIVE_TARGET_KEY",
    "METADATA_CDP_BASE_URL_KEY",
    "METADATA_NEXT_TAB_ID_KEY",
    "METADATA_TABS_KEY",
    "canonicalize_opened_tab",
    "find_tab",
    "host_generation",
    "load_tabs",
    "next_tab_id",
    "set_active_target",
    "store_tabs",
    "tab_from_cdp_payload",
    "tabs_cache_is_fresh",
]
