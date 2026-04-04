from __future__ import annotations

from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from urllib.request import urlopen

from fastapi.testclient import TestClient

from crxzipple.core.config import load_settings
from crxzipple.interfaces.http.app import create_app
from tests.unit.support import SqliteTestHarness, seed_browser_state_root


_LIVE_SMOKE_ENABLED = os.getenv("APP_BROWSER_MCP_LIVE_SMOKE", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
_LIVE_WAIT_MS = max(int(os.getenv("APP_BROWSER_MCP_LIVE_WAIT_MS", "4000")), 1)
_LIVE_BROWSER_PATH = os.getenv("APP_BROWSER_MCP_LIVE_BROWSER", "").strip()


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

class _LivePageServer:
    def __init__(self) -> None:
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _build_handler())
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="browser-live-mcp-page",
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
            body = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>crxzipple mcp smoke</title>
  </head>
  <body>
    <main>
      <label for="query">Query</label>
      <input id="query" type="text" />
      <button id="submit" onclick="document.getElementById('status').textContent = 'Ready';">
        Submit
      </button>
      <p id="status">Waiting</p>
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


@unittest.skipUnless(_LIVE_SMOKE_ENABLED, "MCP live browser smoke test is disabled")
class BrowserLiveMcpSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        browser_binary = _browser_binary()
        if browser_binary is None:
            self.skipTest("No Chromium-compatible browser binary was found.")
        if shutil.which("npx") is None:
            self.skipTest("npx is required for chrome-devtools-mcp live smoke.")

        self._browser_binary = browser_binary
        self._page_server = _LivePageServer()
        self._page_server.start()
        self._profile_dir_context = tempfile.TemporaryDirectory(prefix="crxzipple-live-mcp-profile-")
        self._profile_dir = Path(self._profile_dir_context.name)
        self._browser_process = subprocess.Popen(
            [
                self._browser_binary,
                f"--remote-debugging-address=127.0.0.1",
                "--remote-debugging-port=0",
                f"--user-data-dir={self._profile_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "--headless=new",
                self._page_server.url,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        self._wait_for_cdp_ready()

        self.harness = SqliteTestHarness()
        browser_state_dir = str(Path(self.harness._tempdir.name) / "browser")
        seed_browser_state_root(
            browser_state_dir,
            default_profile="user",
            profiles=[
                {"name": "crxzipple"},
                {
                    "name": "user",
                    "driver": "existing-session",
                    "user_data_dir": str(self._profile_dir),
                    "attach_only": True,
                },
            ],
        )
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            authorization_enabled=False,
            browser_state_dir=browser_state_dir,
            browser_headless=True,
        )
        self.harness.initialize_schema(settings=settings)
        self.client = TestClient(
            create_app(
                settings=settings,
                database_url=self.harness.database_url,
            ),
        )

    def tearDown(self) -> None:
        self.client.close()
        self.client.app.state.container.engine.dispose()
        self.harness.close()
        self._terminate_browser_process()
        self._page_server.close()
        self._profile_dir_context.cleanup()

    def test_existing_session_snapshot_ref_and_actions_flow(self) -> None:
        open_response = self.client.post(
            "/browser/control",
            json={
                "profile_name": "user",
                "kind": "open-tab",
                "payload": {"url": self._page_server.url},
                "timeout_ms": 20_000,
            },
        )
        if open_response.status_code != 200:
            detail = open_response.text
            if "chrome mcp" in detail.lower() or "npx" in detail.lower():
                self.skipTest(detail)
            self.fail(f"open-tab failed: {detail}")
        target_id = open_response.json()["target_id"]

        settle_response = self.client.post(
            "/browser/actions",
            json={
                "profile_name": "user",
                "kind": "wait",
                "target_id": target_id,
                "payload": {"delay_ms": _LIVE_WAIT_MS},
                "timeout_ms": _LIVE_WAIT_MS + 2_000,
            },
        )
        self.assertEqual(settle_response.status_code, 200, settle_response.text)

        snapshot_response = self.client.post(
            "/browser/actions",
            json={
                "profile_name": "user",
                "kind": "snapshot",
                "target_id": target_id,
                "payload": {"format": "interactive", "limit": 50},
                "timeout_ms": 20_000,
            },
        )
        self.assertEqual(snapshot_response.status_code, 200, snapshot_response.text)
        items = snapshot_response.json()["value"]["result"]["value"]
        self.assertTrue(items, "interactive snapshot returned no items")

        query_item = next(
            (item for item in items if item.get("role") in {"textbox", "searchbox"}),
            None,
        )
        button_item = next(
            (item for item in items if item.get("role") == "button"),
            None,
        )
        self.assertIsNotNone(query_item, "interactive snapshot returned no textbox ref")
        self.assertIsNotNone(button_item, "interactive snapshot returned no button ref")

        fill_response = self.client.post(
            "/browser/actions",
            json={
                "profile_name": "user",
                "kind": "fill",
                "target_id": target_id,
                "ref": query_item["ref"],
                "payload": {"text": "smoke"},
                "timeout_ms": 15_000,
            },
        )
        self.assertEqual(fill_response.status_code, 200, fill_response.text)

        click_response = self.client.post(
            "/browser/actions",
            json={
                "profile_name": "user",
                "kind": "click",
                "target_id": target_id,
                "ref": button_item["ref"],
                "timeout_ms": 15_000,
            },
        )
        self.assertEqual(click_response.status_code, 200, click_response.text)

        wait_ready_response = self.client.post(
            "/browser/actions",
            json={
                "profile_name": "user",
                "kind": "wait",
                "target_id": target_id,
                "payload": {"text": "Ready"},
                "timeout_ms": 15_000,
            },
        )
        self.assertEqual(wait_ready_response.status_code, 200, wait_ready_response.text)

        title_response = self.client.post(
            "/browser/actions",
            json={
                "profile_name": "user",
                "kind": "snapshot",
                "target_id": target_id,
                "payload": {"format": "title"},
                "timeout_ms": 15_000,
            },
        )
        self.assertEqual(title_response.status_code, 200, title_response.text)
        self.assertIn("crxzipple mcp smoke", str(title_response.json()["value"]["result"]["value"]).lower())

        close_response = self.client.post(
            "/browser/control",
            json={
                "profile_name": "user",
                "kind": "close-tab",
                "target_id": target_id,
                "timeout_ms": 10_000,
            },
        )
        self.assertEqual(close_response.status_code, 200, close_response.text)

    def _wait_for_cdp_ready(self) -> None:
        deadline = time.monotonic() + 15.0
        port_file = self._profile_dir / "DevToolsActivePort"
        while True:
            if self._browser_process.poll() is not None:
                self.fail("Live smoke browser exited before remote debugging became ready.")
            try:
                if not port_file.is_file():
                    raise FileNotFoundError(str(port_file))
                lines = port_file.read_text(encoding="utf-8").splitlines()
                port = int((lines[0] if lines else "").strip())
                with urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1.0) as response:  # noqa: S310
                    payload = json.loads(response.read().decode("utf-8"))
                if isinstance(payload, dict) and payload.get("webSocketDebuggerUrl"):
                    return
            except Exception:  # noqa: BLE001
                pass
            if time.monotonic() >= deadline:
                self.fail("Timed out waiting for live smoke browser CDP endpoint.")
            time.sleep(0.1)

    def _terminate_browser_process(self) -> None:
        process = getattr(self, "_browser_process", None)
        if process is None:
            return
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=3)
            return
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
