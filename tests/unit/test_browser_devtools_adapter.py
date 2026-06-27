from __future__ import annotations

import math
import unittest

from crxzipple.modules.browser.domain import BrowserValidationError
from crxzipple.modules.browser.infrastructure.devtools import BrowserDevToolsAdapter


class _FakeSession:
    def __init__(self, result: object | None = None) -> None:
        self.detached = False
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.result = result
        self.listeners: dict[str, list[object]] = {}
        self.debugger_scripts: list[dict[str, object]] = []

    def send(self, method: str, params: dict[str, object] | None = None) -> object:
        payload = dict(params or {})
        self.calls.append((method, payload))
        if method == "Debugger.enable":
            for script in self.debugger_scripts:
                self.emit("Debugger.scriptParsed", dict(script))
            return {}
        if method == "Debugger.disable":
            return {}
        if self.result is not None:
            return self.result
        return {"method": method, "params": payload}

    def detach(self) -> None:
        self.detached = True

    def on(self, event_name: str, callback) -> None:  # noqa: ANN001
        self.listeners.setdefault(event_name, []).append(callback)
        self.calls.append(("on", {"event": event_name}))

    def off(self, event_name: str, callback) -> None:  # noqa: ANN001
        listeners = self.listeners.get(event_name, [])
        self.listeners[event_name] = [
            listener for listener in listeners
            if listener is not callback
        ]
        self.calls.append(("off", {"event": event_name}))

    def emit(self, event_name: str, payload: dict[str, object]) -> None:
        for callback in list(self.listeners.get(event_name, [])):
            callback(payload)


class _FailingSession(_FakeSession):
    def send(self, method: str, params: dict[str, object] | None = None) -> object:
        del method, params
        raise RuntimeError(
            "Protocol error: target closed at "
            "https://example.test/a?token=secret-token#frag "
            "Authorization: Bearer secret-token",
        )


class _UrlFailingSession(_FakeSession):
    def send(self, method: str, params: dict[str, object] | None = None) -> object:
        del params
        if method == "Debugger.enable":
            return {}
        raise RuntimeError(
            "Protocol error: failed at "
            "https://example.test/a?token=secret-token#frag "
            "Authorization: Bearer secret-token",
        )


class _FakeContext:
    def __init__(self, session: _FakeSession) -> None:
        self.session = session

    def new_cdp_session(self, page):  # noqa: ANN001
        del page
        return self.session


class _FakePage:
    def __init__(self, session: _FakeSession) -> None:
        self.context = _FakeContext(session)


class BrowserDevToolsAdapterTestCase(unittest.TestCase):
    def test_capture_dom_snapshot_uses_command_session_and_json_payload(self) -> None:
        session = _FakeSession()
        adapter = BrowserDevToolsAdapter()

        result = adapter.capture_dom_snapshot(
            _FakePage(session),
            computed_styles=("display", "visibility"),
            include_dom_rects=True,
        )

        self.assertEqual(result["method"], "DOMSnapshot.captureSnapshot")
        self.assertEqual(
            result["params"],
            {
                "computedStyles": ["display", "visibility"],
                "includeDOMRects": True,
                "includePaintOrder": False,
                "includeBlendedBackgroundColors": False,
            },
        )
        self.assertTrue(session.detached)

    def test_get_node_for_location_maps_native_devtools_params(self) -> None:
        session = _FakeSession()

        BrowserDevToolsAdapter().get_node_for_location(
            _FakePage(session),
            x=12,
            y=34,
            include_user_agent_shadow_dom=True,
            ignore_pointer_events_none=True,
        )

        self.assertEqual(
            session.calls[0],
            (
                "DOM.getNodeForLocation",
                {
                    "x": 12,
                    "y": 34,
                    "includeUserAgentShadowDOM": True,
                    "ignorePointerEventsNone": True,
                },
            ),
        )

    def test_mark_backend_node_resolves_remote_object_and_sets_marker(self) -> None:
        session = _FakeSession(
            result={
                "object": {
                    "objectId": "object-1",
                    "subtype": "node",
                }
            }
        )
        adapter = BrowserDevToolsAdapter()
        page = _FakePage(session)

        def send(method: str, params: dict[str, object] | None = None) -> object:
            payload = dict(params or {})
            session.calls.append((method, payload))
            if method == "DOM.resolveNode":
                return {
                    "object": {
                        "objectId": "object-1",
                        "subtype": "node",
                    }
                }
            return {"result": {"value": {"ok": True, "tag": "button"}}}

        session.send = send  # type: ignore[method-assign]

        result = adapter.mark_backend_node(
            page,
            backend_node_id=42,
            attribute_name="data-crxzipple-backend-ref",
            attribute_value="ref-r1-42-1",
        )

        self.assertEqual(result["ok"], True)
        self.assertEqual(
            session.calls,
            [
                ("DOM.resolveNode", {"backendNodeId": 42}),
                (
                    "Runtime.callFunctionOn",
                    {
                        "objectId": "object-1",
                        "functionDeclaration": session.calls[1][1]["functionDeclaration"],
                        "arguments": [
                            {"value": "data-crxzipple-backend-ref"},
                            {"value": "ref-r1-42-1"},
                        ],
                        "returnByValue": True,
                        "awaitPromise": False,
                    },
                ),
            ],
        )

    def test_event_listeners_and_script_source_are_thin_cdp_wrappers(self) -> None:
        session = _FakeSession()
        adapter = BrowserDevToolsAdapter()
        page = _FakePage(session)

        adapter.get_event_listeners_for_object(
            page,
            object_id="object-1",
            depth=2,
            pierce=True,
        )
        adapter.read_script_source(page, script_id="script-1")

        self.assertEqual(
            session.calls,
            [
                (
                    "DOMDebugger.getEventListeners",
                    {"objectId": "object-1", "depth": 2, "pierce": True},
                ),
                ("Debugger.enable", {}),
                ("Debugger.getScriptSource", {"scriptId": "script-1"}),
                ("Debugger.disable", {}),
            ],
        )
        self.assertTrue(session.detached)

    def test_get_event_listeners_for_backend_node_resolves_object_first(self) -> None:
        session = _FakeSession()
        adapter = BrowserDevToolsAdapter()
        page = _FakePage(session)

        def send(method: str, params: dict[str, object] | None = None) -> object:
            payload = dict(params or {})
            session.calls.append((method, payload))
            if method == "DOM.resolveNode":
                return {
                    "object": {
                        "objectId": "object-42",
                        "subtype": "node",
                    }
                }
            return {
                "listeners": [
                    {
                        "type": "click",
                        "scriptId": "17",
                        "lineNumber": 12,
                    }
                ]
            }

        session.send = send  # type: ignore[method-assign]

        result = adapter.get_event_listeners_for_backend_node(
            page,
            backend_node_id=42,
            depth=1,
            pierce=True,
        )

        self.assertEqual(result["backend_node_id"], 42)
        self.assertEqual(result["object"]["objectId"], "object-42")
        self.assertEqual(result["listeners"][0]["type"], "click")
        self.assertEqual(
            session.calls,
            [
                ("DOM.resolveNode", {"backendNodeId": 42}),
                (
                    "DOMDebugger.getEventListeners",
                    {"objectId": "object-42", "depth": 1, "pierce": True},
                ),
            ],
        )

    def test_collect_debugger_scripts_enables_debugger_and_returns_script_events(self) -> None:
        session = _FakeSession()
        session.debugger_scripts = [
            {
                "scriptId": "1",
                "url": "https://example.test/app.js",
                "startLine": 0,
            },
            {
                "scriptId": "2",
                "url": "",
                "startLine": 10,
            },
        ]

        scripts = BrowserDevToolsAdapter().collect_debugger_scripts(
            _FakePage(session),
            wait_ms=0,
        )

        self.assertEqual(
            scripts,
            [
                {
                    "scriptId": "1",
                    "url": "https://example.test/app.js",
                    "startLine": 0,
                },
                {
                    "scriptId": "2",
                    "url": "",
                    "startLine": 10,
                },
            ],
        )
        self.assertEqual(
            [call[0] for call in session.calls],
            [
                "on",
                "Debugger.enable",
                "Runtime.evaluate",
                "off",
                "Debugger.disable",
            ],
        )
        self.assertTrue(session.detached)

    def test_rejects_non_json_safe_payload_before_sending(self) -> None:
        session = _FakeSession()

        with self.assertRaisesRegex(BrowserValidationError, "must be JSON-safe"):
            BrowserDevToolsAdapter().capture_dom_snapshot(
                _FakePage(session),
                computed_styles=("display", math.nan),
            )

        self.assertEqual(session.calls, [])
        self.assertFalse(session.detached)

    def test_devtools_errors_remain_display_safe(self) -> None:
        with self.assertRaises(BrowserValidationError) as exc_info:
            BrowserDevToolsAdapter().read_script_source(
                _FakePage(_FailingSession()),
                script_id="script-1",
            )

        message = str(exc_info.exception)
        self.assertIn("Browser target is no longer available", message)
        self.assertIn("Next: reconcile the browser context lease", message)
        self.assertNotIn("secret-token", message)
        self.assertNotIn("#frag", message)

    def test_generic_devtools_errors_remain_display_safe(self) -> None:
        with self.assertRaises(BrowserValidationError) as exc_info:
            BrowserDevToolsAdapter().read_script_source(
                _FakePage(_UrlFailingSession()),
                script_id="script-1",
        )

        message = str(exc_info.exception)
        self.assertIn("Browser CDP Debugger.getScriptSource failed", message)
        self.assertIn("https://example.test/a?[redacted]", message)
        self.assertIn("Authorization: [redacted]", message)
        self.assertNotIn("secret-token", message)
        self.assertNotIn("#frag", message)


if __name__ == "__main__":
    unittest.main()
