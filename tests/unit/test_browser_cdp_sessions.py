from __future__ import annotations

import unittest

from crxzipple.modules.browser.domain import BrowserValidationError
from crxzipple.modules.browser.infrastructure.cdp_sessions import (
    BrowserCdpSessionBroker,
    display_safe_cdp_error,
)


class _FakeSession:
    def __init__(self) -> None:
        self.detached = False
        self.listeners: dict[str, list[object]] = {}

    def send(self, method: str, params: dict[str, object] | None = None) -> dict[str, object]:
        return {"method": method, "params": dict(params or {})}

    def detach(self) -> None:
        self.detached = True

    def on(self, event_name: str, callback) -> None:  # noqa: ANN001
        self.listeners.setdefault(event_name, []).append(callback)


class _FailingSession(_FakeSession):
    def send(self, method: str, params: dict[str, object] | None = None) -> dict[str, object]:
        del method, params
        raise RuntimeError("Protocol error: target closed at https://example.com/a?token=secret")


class _FakeContext:
    def __init__(self, session: _FakeSession) -> None:
        self.session = session

    def new_cdp_session(self, page):  # noqa: ANN001
        return self.session


class _FakePage:
    target_id = "tab-1"

    def __init__(self, session: _FakeSession) -> None:
        self.context = _FakeContext(session)


class BrowserCdpSessionBrokerTestCase(unittest.TestCase):
    def test_broker_distinguishes_command_and_subscription_sessions(self) -> None:
        broker = BrowserCdpSessionBroker()
        command_session = _FakeSession()
        subscription_session = _FakeSession()

        command = broker.open_command_session(
            _FakePage(command_session),
            operation="Runtime.evaluate",
        )
        subscription = broker.open_subscription_session(
            _FakePage(subscription_session),
            operation="Network capture",
        )

        self.assertEqual(command.mode, "command")
        self.assertEqual(command.target_id, "tab-1")
        self.assertEqual(subscription.mode, "subscription")
        subscription.on("Network.requestWillBeSent", object())
        self.assertIn("Network.requestWillBeSent", subscription_session.listeners)
        broker.detach(command)
        broker.detach(subscription)
        self.assertTrue(command_session.detached)
        self.assertTrue(subscription_session.detached)

    def test_command_session_detaches_when_body_raises(self) -> None:
        broker = BrowserCdpSessionBroker()
        raw_session = _FakeSession()

        with self.assertRaisesRegex(RuntimeError, "action failed"):
            with broker.command_session(
                _FakePage(raw_session),
                operation="Runtime.evaluate",
            ) as lease:
                self.assertFalse(lease.detached)
                raise RuntimeError("action failed")

        self.assertTrue(raw_session.detached)

    def test_cdp_command_errors_are_display_safe_and_actionable(self) -> None:
        broker = BrowserCdpSessionBroker()
        lease = broker.open_command_session(
            _FakePage(_FailingSession()),
            operation="Runtime.evaluate",
        )

        with self.assertRaises(BrowserValidationError) as exc_info:
            broker.send_command(lease, "Runtime.evaluate", {"expression": "1 + 1"})

        message = str(exc_info.exception)
        self.assertIn("Browser target is no longer available", message)
        self.assertIn("Next: reconcile the browser context lease", message)
        self.assertNotIn("token=secret", message)

    def test_generic_cdp_errors_redact_url_query_strings(self) -> None:
        message = display_safe_cdp_error(
            RuntimeError("failed to inspect https://example.com/path?token=secret#frag"),
            operation="Network.getResponseBody",
        )

        self.assertIn("Browser CDP Network.getResponseBody failed", message)
        self.assertIn("https://example.com/path?[redacted]", message)
        self.assertNotIn("token=secret", message)


if __name__ == "__main__":
    unittest.main()
