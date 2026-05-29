from __future__ import annotations

from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import socket
import threading
import time
import unittest
from urllib.request import urlopen

from fastapi.testclient import TestClient

from crxzipple.core.config import load_settings
from crxzipple.interfaces.http.app import create_app
from crxzipple.interfaces.runtime_container import AppKey
from tests.unit.support import SqliteTestHarness


_LIVE_SMOKE_ENABLED = os.getenv("APP_BROWSER_LIVE_SMOKE", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
_LIVE_BROWSER_PATH = os.getenv("APP_BROWSER_LIVE_BROWSER", "").strip()
_LIVE_SMOKE_WAIT_MS = max(int(os.getenv("APP_BROWSER_LIVE_WAIT_MS", "4000")), 1)


def _browser_binary() -> str | None:
    if _LIVE_BROWSER_PATH:
        candidate = Path(_LIVE_BROWSER_PATH).expanduser()
        if candidate.is_file():
            return str(candidate.resolve())
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.is_file():
            return str(path.resolve())
    return None


class _LiveIframePageServer:
    def __init__(self) -> None:
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _build_handler())
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="browser-live-iframe-page",
            daemon=True,
        )

    @property
    def url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}/"

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)


def _build_handler() -> type[BaseHTTPRequestHandler]:
    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path.startswith("/frame"):
                body = """
<!doctype html>
<html>
  <head><meta charset="utf-8" /><title>crxzipple iframe child</title></head>
  <body>
    <main>
      <button id="inside-frame">Inside Frame</button>
      <p id="frame-status">Ready</p>
    </main>
  </body>
</html>
""".strip()
            else:
                body = """
<!doctype html>
<html>
  <head><meta charset="utf-8" /><title>crxzipple iframe smoke</title></head>
  <body>
    <main>
      <h1>Browser iframe smoke</h1>
      <iframe id="g_iframe" title="Smoke Frame" src="/frame"></iframe>
    </main>
  </body>
</html>
""".strip()
            encoded = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            del format, args
            return None

    return _Handler


def _interactive_refs(snapshot_payload: dict[str, object]) -> list[dict[str, object]]:
    value = snapshot_payload["value"]["result"]["value"]  # type: ignore[index]
    if isinstance(value, dict):
        refs = value.get("refs")
        if isinstance(refs, list):
            return [item for item in refs if isinstance(item, dict)]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


@unittest.skipUnless(_LIVE_SMOKE_ENABLED, "live browser smoke test is disabled")
class BrowserLiveIframeSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        browser_binary = _browser_binary()
        if browser_binary is None:
            self.skipTest("No Chromium-compatible browser binary was found.")
        self._page_server = _LiveIframePageServer()
        self._page_server.start()
        self.harness = SqliteTestHarness()
        self._env_before = {
            key: os.environ.get(key)
            for key in (
                "APP_DATABASE_URL",
                "APP_BROWSER_STATE_DIR",
                "APP_DAEMON_STATE_DIR",
                "PYTHONPATH",
            )
        }
        browser_state_dir = str(Path(self.harness._tempdir.name) / "browser")
        daemon_state_dir = str(Path(self.harness._tempdir.name) / "daemon")
        cdp_port = _free_loopback_port()
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            authorization_enabled=False,
            browser_state_dir=browser_state_dir,
            daemon_state_dir=daemon_state_dir,
            browser_executable_path=browser_binary,
            browser_cdp_port=cdp_port,
            browser_headless=True,
        )
        os.environ["APP_DATABASE_URL"] = self.harness.database_url
        os.environ["APP_BROWSER_STATE_DIR"] = browser_state_dir
        os.environ["APP_DAEMON_STATE_DIR"] = daemon_state_dir
        os.environ["PYTHONPATH"] = os.environ.get("PYTHONPATH") or "src"
        self.harness.initialize_schema(settings=settings)
        self.client = TestClient(
            create_app(
                settings=settings,
                database_url=self.harness.database_url,
            ),
        )
        self._cdp_endpoint = f"http://127.0.0.1:{cdp_port}"
        manager = self.client.app.state.container.require(AppKey.DAEMON_MANAGER)
        manager.ensure_service("host:browser:crxzipple")
        self._wait_for_cdp_ready(self._cdp_endpoint)

    def tearDown(self) -> None:
        stop_error: Exception | None = None
        try:
            manager = self.client.app.state.container.require(AppKey.DAEMON_MANAGER)
            manager.stop_service("host:browser:crxzipple")
            self._wait_for_cdp_stopped(self._cdp_endpoint)
        except Exception as exc:  # noqa: BLE001
            stop_error = exc
        try:
            database_engine = self.client.app.state.container.require(AppKey.DATABASE_ENGINE)
            self.client.close()
            database_engine.dispose()
        finally:
            self._remove_temp_lock_files()
            self.harness.close()
            self._page_server.close()
            for key, value in self._env_before.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        if stop_error is not None:
            raise stop_error

    def test_managed_daemon_host_iframe_snapshot_ref_and_action_flow(self) -> None:
        open_response = self.client.post(
            "/browser/control",
            json={
                "kind": "open-tab",
                "payload": {"url": self._page_server.url},
                "timeout_ms": 15_000,
            },
        )
        if open_response.status_code != 200:
            detail = open_response.text
            if "executable" in detail.lower() or "cdp" in detail.lower():
                self.skipTest(detail)
            self.fail(f"open-tab failed: {detail}")
        target_id = open_response.json()["target_id"]

        wait_iframe_response = self.client.post(
            "/browser/actions",
            json={
                "kind": "wait",
                "target_id": target_id,
                "selector": "#g_iframe",
                "payload": {"state": "visible"},
                "timeout_ms": 15_000,
            },
        )
        self.assertEqual(wait_iframe_response.status_code, 200, wait_iframe_response.text)

        settle_response = self.client.post(
            "/browser/actions",
            json={
                "kind": "wait",
                "target_id": target_id,
                "payload": {"delay_ms": _LIVE_SMOKE_WAIT_MS},
                "timeout_ms": _LIVE_SMOKE_WAIT_MS + 2_000,
            },
        )
        self.assertEqual(settle_response.status_code, 200, settle_response.text)

        snapshot_response = self.client.post(
            "/browser/actions",
            json={
                "kind": "snapshot",
                "target_id": target_id,
                "payload": {"format": "interactive", "limit": 200},
                "timeout_ms": 20_000,
            },
        )
        self.assertEqual(snapshot_response.status_code, 200, snapshot_response.text)
        snapshot_payload = snapshot_response.json()
        items = _interactive_refs(snapshot_payload)
        self.assertTrue(items, "interactive snapshot returned no items")

        frame_items = [item for item in items if item.get("frame_path")]
        self.assertTrue(frame_items, "interactive snapshot returned no child-frame refs")
        target_item = frame_items[0]

        action_response = self.client.post(
            "/browser/actions",
            json={
                "kind": "scroll-into-view",
                "target_id": target_id,
                "ref": target_item["ref"],
                "timeout_ms": 15_000,
            },
        )
        self.assertEqual(action_response.status_code, 200, action_response.text)
        action_payload = action_response.json()
        self.assertTrue(action_payload["ok"])
        self.assertEqual(action_payload["value"]["frame_path"], target_item["frame_path"])

        close_response = self.client.post(
            "/browser/control",
            json={
                "kind": "close-tab",
                "target_id": target_id,
                "timeout_ms": 10_000,
            },
        )
        self.assertEqual(close_response.status_code, 200, close_response.text)

    def _wait_for_cdp_ready(self, endpoint: str) -> None:
        deadline = time.monotonic() + 20.0
        while True:
            try:
                with urlopen(f"{endpoint}/json/version", timeout=1.0) as response:  # noqa: S310
                    payload = response.read().decode("utf-8")
                if "webSocketDebuggerUrl" in payload:
                    return
            except Exception:  # noqa: BLE001
                pass
            if time.monotonic() >= deadline:
                self.fail(f"Timed out waiting for managed browser CDP endpoint {endpoint}.")
            time.sleep(0.1)

    def _wait_for_cdp_stopped(self, endpoint: str) -> None:
        deadline = time.monotonic() + 10.0
        while True:
            try:
                with urlopen(f"{endpoint}/json/version", timeout=0.5):  # noqa: S310
                    pass
            except Exception:  # noqa: BLE001
                return
            if time.monotonic() >= deadline:
                self.fail(f"Timed out waiting for managed browser CDP endpoint {endpoint} to stop.")
            time.sleep(0.1)

    def _remove_temp_lock_files(self) -> None:
        root = Path(self.harness._tempdir.name)
        for path in root.rglob("*.lock"):
            path.unlink(missing_ok=True)


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
