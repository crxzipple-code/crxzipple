from __future__ import annotations

from dataclasses import dataclass, field
from threading import enumerate as list_threads
from threading import current_thread
from threading import RLock
from threading import get_ident
from typing import Any

from playwright.sync_api import sync_playwright

from crxzipple.modules.browser.domain import BrowserValidationError, ResolvedBrowserProfile
from .cdp_urls import browser_ref_to_cdp_http_base, normalize_cdp_http_base


@dataclass(slots=True)
class _ThreadPlaywrightState:
    owner_thread_id: int = 0
    owner_thread: Any = None
    playwright_manager: Any = None
    playwright: Any = None
    browsers: dict[str, Any] = field(default_factory=dict)
    browser_urls: dict[str, str] = field(default_factory=dict)
    pages_by_profile: dict[str, dict[str, Any]] = field(default_factory=dict)
    target_ids_by_page: dict[int, str] = field(default_factory=dict)


@dataclass(slots=True)
class PlaywrightCdpSessionPool:
    connect_timeout_ms: int = 5_000
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)
    _thread_states: dict[int, _ThreadPlaywrightState] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    def resolve_page(
        self,
        *,
        profile: ResolvedBrowserProfile,
        target_id: str,
        timeout_ms: int | None = None,
        cdp_url: str | None = None,
    ):
        state = self._thread_state()
        browser = self._browser_for(
            profile=profile,
            timeout_ms=timeout_ms,
            cdp_url=cdp_url,
            state=state,
        )
        cached_page = self._cached_page(
            state=state,
            profile_name=profile.name,
            target_id=target_id,
            browser=browser,
        )
        if cached_page is not None:
            return cached_page

        pages = self._refresh_profile_pages(
            state=state,
            profile_name=profile.name,
            browser=browser,
        )
        page = pages.get(target_id)
        if page is not None:
            return page
        raise BrowserValidationError(
            f"Browser tab '{target_id}' is not available through Playwright CDP.",
        )

    def clear_profile(self, *, profile_name: str) -> None:
        browsers: list[Any] = []
        with self._lock:
            self._reap_stale_states()
            active_thread = current_thread()
            for state in self._thread_states.values():
                browser = state.browsers.pop(profile_name, None)
                state.browser_urls.pop(profile_name, None)
                self._clear_profile_page_cache(state=state, profile_name=profile_name)
                if browser is not None and state.owner_thread is active_thread:
                    browsers.append(browser)
        for browser in browsers:
            self._close_browser(browser)

    def close(self) -> None:
        with self._lock:
            self._reap_stale_states()
            active_thread = current_thread()
            current_thread_id = get_ident()
            current_state = self._thread_states.pop(current_thread_id, None)
            if current_state is not None and current_state.owner_thread is not active_thread:
                current_state = None
            self._thread_states.clear()
        managers: list[Any] = []
        browsers: list[Any] = []
        if current_state is not None:
            browsers.extend(current_state.browsers.values())
            if current_state.playwright_manager is not None:
                managers.append(current_state.playwright_manager)
        for browser in browsers:
            self._close_browser(browser)
        for manager in managers:
            try:
                manager.stop()
            except Exception:  # noqa: BLE001
                pass

    def _browser_for(
        self,
        *,
        profile: ResolvedBrowserProfile,
        timeout_ms: int | None,
        cdp_url: str | None = None,
        state: _ThreadPlaywrightState | None = None,
    ):
        effective_cdp_url = self._normalize_cdp_url(
            profile=profile,
            cdp_url=cdp_url,
        )
        if not effective_cdp_url:
            raise BrowserValidationError(
                f"Browser profile '{profile.name}' does not define a CDP URL.",
            )

        state = state or self._thread_state()
        with self._lock:
            cached = state.browsers.get(profile.name)
            cached_url = state.browser_urls.get(profile.name)
            if (
                cached is not None
                and cached_url == effective_cdp_url
                and self._browser_is_connected(cached)
            ):
                return cached

            if cached is not None:
                self._close_browser(cached)
                state.browsers.pop(profile.name, None)
                state.browser_urls.pop(profile.name, None)
                self._clear_profile_page_cache(state=state, profile_name=profile.name)

            playwright = self._ensure_playwright(state)
            try:
                browser = playwright.chromium.connect_over_cdp(
                    effective_cdp_url,
                    timeout=timeout_ms or self.connect_timeout_ms,
                )
            except Exception as exc:  # noqa: BLE001
                raise BrowserValidationError(
                    f"Playwright could not connect over CDP to '{effective_cdp_url}': {exc}",
                ) from exc
            state.browsers[profile.name] = browser
            state.browser_urls[profile.name] = effective_cdp_url
            self._clear_profile_page_cache(state=state, profile_name=profile.name)
            return browser

    def _ensure_playwright(self, state: _ThreadPlaywrightState):
        if state.playwright is not None:
            return state.playwright
        manager = sync_playwright()
        state.playwright_manager = manager
        state.playwright = manager.start()
        return state.playwright

    def _thread_state(self) -> _ThreadPlaywrightState:
        thread = current_thread()
        thread_id = get_ident()
        with self._lock:
            self._reap_stale_states()
            state = self._thread_states.get(thread_id)
            if state is None or state.owner_thread is not thread:
                state = _ThreadPlaywrightState(
                    owner_thread_id=thread_id,
                    owner_thread=thread,
                )
                self._thread_states[thread_id] = state
            return state

    @staticmethod
    def _normalize_cdp_url(
        *,
        profile: ResolvedBrowserProfile,
        cdp_url: str | None,
    ) -> str:
        normalized = (cdp_url or "").strip()
        if normalized:
            return normalize_cdp_http_base(normalized)
        return normalize_cdp_http_base(profile.cdp_url)

    @staticmethod
    def browser_ref_to_cdp_url(browser_ref: str | None) -> str | None:
        return browser_ref_to_cdp_http_base(browser_ref)

    def _reap_stale_states(self) -> None:
        live_threads = {
            thread
            for thread in list_threads()
            if thread.ident is not None and thread.is_alive()
        }
        stale_thread_ids = [
            thread_id
            for thread_id, state in self._thread_states.items()
            if state.owner_thread not in live_threads
        ]
        for thread_id in stale_thread_ids:
            self._thread_states.pop(thread_id, None)

    def _cached_page(
        self,
        *,
        state: _ThreadPlaywrightState,
        profile_name: str,
        target_id: str,
        browser,
    ):
        with self._lock:
            profile_pages = state.pages_by_profile.get(profile_name, {})
            page = profile_pages.get(target_id)
            if page is None:
                return None
            if not self._browser_is_connected(browser) or self._page_is_closed(page):
                self._clear_profile_page_cache(state=state, profile_name=profile_name)
                return None
            return page

    def _refresh_profile_pages(
        self,
        *,
        state: _ThreadPlaywrightState,
        profile_name: str,
        browser,
    ) -> dict[str, Any]:
        resolved: dict[str, Any] = {}
        for context in tuple(browser.contexts):
            for page in tuple(context.pages):
                if self._page_is_closed(page):
                    continue
                target_id = self._page_target_id(page, state=state)
                if target_id is None:
                    continue
                resolved[target_id] = page
        with self._lock:
            self._clear_profile_page_cache(state=state, profile_name=profile_name)
            state.pages_by_profile[profile_name] = dict(resolved)
            for target_id, page in resolved.items():
                if target_id:
                    state.target_ids_by_page[id(page)] = target_id
        return resolved

    @staticmethod
    def _clear_profile_page_cache(
        *,
        state: _ThreadPlaywrightState,
        profile_name: str,
    ) -> None:
        profile_pages = state.pages_by_profile.pop(profile_name, {})
        for page in profile_pages.values():
            state.target_ids_by_page.pop(id(page), None)

    def _page_target_id(
        self,
        page,  # noqa: ANN001
        *,
        state: _ThreadPlaywrightState,
    ) -> str | None:
        cached = state.target_ids_by_page.get(id(page))
        if cached:
            return cached
        session = page.context.new_cdp_session(page)
        try:
            payload = session.send("Target.getTargetInfo")
        except Exception as exc:  # noqa: BLE001
            raise BrowserValidationError(
                f"Playwright could not resolve the CDP target id for a page: {exc}",
            ) from exc
        finally:
            detach = getattr(session, "detach", None)
            if callable(detach):
                try:
                    detach()
                except Exception:  # noqa: BLE001
                    pass
        if not isinstance(payload, dict):
            return None
        target_info = payload.get("targetInfo")
        if not isinstance(target_info, dict):
            return None
        target_id = target_info.get("targetId")
        if not isinstance(target_id, str):
            return None
        normalized = target_id.strip()
        if normalized:
            state.target_ids_by_page[id(page)] = normalized
            return normalized
        return None

    @staticmethod
    def _browser_is_connected(browser) -> bool:  # noqa: ANN001
        is_connected = getattr(browser, "is_connected", None)
        if callable(is_connected):
            try:
                return bool(is_connected())
            except Exception:  # noqa: BLE001
                return False
        return True

    @staticmethod
    def _close_browser(browser) -> None:  # noqa: ANN001
        close = getattr(browser, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def _page_is_closed(page) -> bool:  # noqa: ANN001
        is_closed = getattr(page, "is_closed", None)
        if callable(is_closed):
            try:
                return bool(is_closed())
            except Exception:  # noqa: BLE001
                return True
        return False
