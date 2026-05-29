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
        self._event_listeners: dict[str, list[object]] = {}

    def is_closed(self) -> bool:
        return self._closed

    def on(self, event_name: str, callback) -> None:  # noqa: ANN001
        listeners = self._event_listeners.setdefault(event_name, [])
        listeners.append(callback)

    def emit_console(
        self,
        *,
        message_type: str,
        text: str,
        location: dict[str, object] | None = None,
    ) -> None:
        class _FakeConsoleMessage:
            def __init__(self, *, message_type: str, text: str, location: dict[str, object] | None) -> None:
                self.type = message_type
                self.text = text
                self.location = dict(location or {})

        message = _FakeConsoleMessage(
            message_type=message_type,
            text=text,
            location=location,
        )
        for callback in list(self._event_listeners.get("console", ())):
            callback(message)


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
    def __init__(
        self,
        connect_calls: list[tuple[str, int]],
        target_sequence: list[str] | None = None,
    ) -> None:
        self._connect_calls = connect_calls
        self._target_sequence = target_sequence if target_sequence is not None else ["tab-1"]

    def connect_over_cdp(self, cdp_url: str, timeout: int):  # noqa: ANN001
        self._connect_calls.append((cdp_url, timeout))
        if len(self._target_sequence) > 1:
            target_id = self._target_sequence.pop(0)
        else:
            target_id = self._target_sequence[0]
        return _FakeBrowser(target_id=target_id)


class _FakePlaywright:
    def __init__(
        self,
        connect_calls: list[tuple[str, int]],
        target_sequence: list[str] | None = None,
    ) -> None:
        self.chromium = _FakeChromium(connect_calls, target_sequence=target_sequence)


class _FakeManager:
    def __init__(
        self,
        connect_calls: list[tuple[str, int]],
        target_sequence: list[str] | None = None,
    ) -> None:
        self._connect_calls = connect_calls
        self._target_sequence = target_sequence
        self.stopped = False

    def start(self) -> _FakePlaywright:
        return _FakePlaywright(
            self._connect_calls,
            target_sequence=self._target_sequence,
        )

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

    def test_resolve_page_reconnects_when_cached_cdp_browser_misses_target(self) -> None:
        connect_calls: list[tuple[str, int]] = []
        target_sequence = ["old-tab", "tab-1"]

        def _fake_sync_playwright() -> _FakeManager:
            return _FakeManager(connect_calls, target_sequence=target_sequence)

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
                page = pool.resolve_page(profile=profile, target_id="tab-1")

                self.assertEqual(page.target_id, "tab-1")
                self.assertEqual(
                    connect_calls,
                    [
                        ("http://127.0.0.1:18800", 1234),
                        ("http://127.0.0.1:18800", 1234),
                    ],
                )
            finally:
                pool.close()

    def test_console_messages_are_captured_and_can_be_cleared(self) -> None:
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
                page = pool.resolve_page(profile=profile, target_id="tab-1")
                page.emit_console(
                    message_type="warning",
                    text="Route fallback",
                    location={"url": "https://example.com/app.js", "lineNumber": 12, "columnNumber": 4},
                )

                messages = pool.get_console_messages(page=page, level="warn")
                self.assertEqual(len(messages), 1)
                self.assertEqual(messages[0]["level"], "warn")
                self.assertEqual(messages[0]["text"], "Route fallback")
                self.assertEqual(
                    messages[0]["location"],
                    {
                        "url": "https://example.com/app.js",
                        "line_number": 12,
                        "column_number": 4,
                    },
                )

                cleared = pool.get_console_messages(page=page, clear=True)
                self.assertEqual(len(cleared), 1)
                self.assertEqual(pool.get_console_messages(page=page), [])
            finally:
                pool.close()


if __name__ == "__main__":
    unittest.main()
