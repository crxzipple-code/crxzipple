from __future__ import annotations

import threading
import unittest
from unittest.mock import patch

from crxzipple.modules.browser.domain import ResolvedBrowserProfile
from crxzipple.modules.browser.infrastructure import PlaywrightCdpSessionPool


class _FakeCdpSession:
    def __init__(self, target_id: str) -> None:
        self.target_id = target_id

    def send(self, method: str):  # noqa: ANN001
        if method != "Target.getTargetInfo":
            raise AssertionError(method)
        return {"targetInfo": {"targetId": self.target_id}}

    def detach(self) -> None:
        return None


class _FakeContext:
    def __init__(self, target_id: str) -> None:
        self.pages = [_FakePage(self, target_id)]
        self.cdp_session_calls = 0

    def new_cdp_session(self, page):  # noqa: ANN001
        self.cdp_session_calls += 1
        return _FakeCdpSession(page.target_id)


class _FakePage:
    def __init__(self, context: _FakeContext, target_id: str) -> None:
        self.context = context
        self.target_id = target_id
        self._closed = False

    def is_closed(self) -> bool:
        return self._closed


class _FakeBrowser:
    def __init__(self, target_id: str) -> None:
        self.contexts = [_FakeContext(target_id)]
        self._closed = False
        self.owner_thread_id = threading.get_ident()

    def is_connected(self) -> bool:
        return not self._closed

    def close(self) -> None:
        if threading.get_ident() != self.owner_thread_id:
            raise RuntimeError("cross-thread close")
        self._closed = True


class _FakeChromium:
    def __init__(self, connect_calls: list[tuple[str, int]]) -> None:
        self._connect_calls = connect_calls

    def connect_over_cdp(self, cdp_url: str, timeout: int):  # noqa: ANN001
        self._connect_calls.append((cdp_url, timeout))
        return _FakeBrowser(target_id="tab-1")


class _FakePlaywright:
    def __init__(self, connect_calls: list[tuple[str, int]]) -> None:
        self.chromium = _FakeChromium(connect_calls)


class _FakeManager:
    def __init__(self, connect_calls: list[tuple[str, int]]) -> None:
        self._connect_calls = connect_calls
        self.stopped = False

    def start(self) -> _FakePlaywright:
        return _FakePlaywright(self._connect_calls)

    def stop(self) -> None:
        self.stopped = True


class BrowserPlaywrightPoolTestCase(unittest.TestCase):
    def test_pool_is_thread_local_per_profile(self) -> None:
        connect_calls: list[tuple[str, int]] = []

        def _fake_sync_playwright() -> _FakeManager:
            return _FakeManager(connect_calls)

        profile = ResolvedBrowserProfile(
            name="crxzipple",
            driver="managed",
            cdp_url="http://127.0.0.1:18800",
            cdp_port=18800,
            user_data_dir=None,
            attach_only=False,
            is_loopback=True,
        )

        with patch(
            "crxzipple.modules.browser.infrastructure.playwright.sync_playwright",
            _fake_sync_playwright,
        ):
            pool = PlaywrightCdpSessionPool(connect_timeout_ms=1234)
            try:
                first_page = pool.resolve_page(profile=profile, target_id="tab-1")
                second_page = pool.resolve_page(profile=profile, target_id="tab-1")

                worker_pages: list[object] = []

                def _resolve_in_thread() -> None:
                    worker_pages.append(
                        pool.resolve_page(profile=profile, target_id="tab-1")
                    )

                worker = threading.Thread(target=_resolve_in_thread)
                worker.start()
                worker.join(timeout=5)

                self.assertEqual(len(connect_calls), 2)
                self.assertIs(first_page, second_page)
                self.assertEqual(first_page.context.cdp_session_calls, 1)
                self.assertEqual(len(worker_pages), 1)
                self.assertIsNot(first_page, worker_pages[0])
            finally:
                pool.close()

    def test_clear_profile_and_close_do_not_close_worker_owned_browser_from_main_thread(self) -> None:
        connect_calls: list[tuple[str, int]] = []

        def _fake_sync_playwright() -> _FakeManager:
            return _FakeManager(connect_calls)

        profile = ResolvedBrowserProfile(
            name="crxzipple",
            driver="managed",
            cdp_url="http://127.0.0.1:18800",
            cdp_port=18800,
            user_data_dir=None,
            attach_only=False,
            is_loopback=True,
        )

        with patch(
            "crxzipple.modules.browser.infrastructure.playwright.sync_playwright",
            _fake_sync_playwright,
        ):
            pool = PlaywrightCdpSessionPool(connect_timeout_ms=1234)
            worker = threading.Thread(
                target=lambda: pool.resolve_page(profile=profile, target_id="tab-1"),
            )
            worker.start()
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive())

            pool.clear_profile(profile_name=profile.name)
            pool.close()

    def test_pool_recreates_state_when_thread_ident_is_reused(self) -> None:
        connect_calls: list[tuple[str, int]] = []

        def _fake_sync_playwright() -> _FakeManager:
            return _FakeManager(connect_calls)

        class _FakeThread:
            def __init__(self, label: str) -> None:
                self.label = label
                self.ident = 777

            def is_alive(self) -> bool:
                return True

            def __hash__(self) -> int:
                return hash(self.label)

        profile = ResolvedBrowserProfile(
            name="crxzipple",
            driver="managed",
            cdp_url="http://127.0.0.1:18800",
            cdp_port=18800,
            user_data_dir=None,
            attach_only=False,
            is_loopback=True,
        )

        first_thread = _FakeThread("first")
        second_thread = _FakeThread("second")

        with patch(
            "crxzipple.modules.browser.infrastructure.playwright.sync_playwright",
            _fake_sync_playwright,
        ):
            pool = PlaywrightCdpSessionPool(connect_timeout_ms=1234)
            try:
                with (
                    patch(
                        "crxzipple.modules.browser.infrastructure.playwright.get_ident",
                        return_value=777,
                    ),
                    patch(
                        "crxzipple.modules.browser.infrastructure.playwright.current_thread",
                        return_value=first_thread,
                    ),
                    patch(
                        "crxzipple.modules.browser.infrastructure.playwright.list_threads",
                        return_value=[first_thread],
                    ),
                ):
                    pool.resolve_page(profile=profile, target_id="tab-1")

                with (
                    patch(
                        "crxzipple.modules.browser.infrastructure.playwright.get_ident",
                        return_value=777,
                    ),
                    patch(
                        "crxzipple.modules.browser.infrastructure.playwright.current_thread",
                        return_value=second_thread,
                    ),
                    patch(
                        "crxzipple.modules.browser.infrastructure.playwright.list_threads",
                        return_value=[second_thread],
                    ),
                ):
                    pool.resolve_page(profile=profile, target_id="tab-1")

                self.assertEqual(len(connect_calls), 2)
            finally:
                pool.close()


if __name__ == "__main__":
    unittest.main()
