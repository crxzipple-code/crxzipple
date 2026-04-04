from __future__ import annotations

from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import socket
import socketserver
import subprocess
import tempfile
import threading
import time
import unittest
from urllib.request import ProxyHandler, build_opener, urlopen

from fastapi.testclient import TestClient

from crxzipple.core.config import load_settings
from crxzipple.interfaces.http.app import create_app
from tests.unit.support import SqliteTestHarness, seed_browser_state_root


_LIVE_SMOKE_ENABLED = os.getenv("APP_BROWSER_REMOTE_CDP_LIVE_SMOKE", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
_LIVE_WAIT_MS = max(int(os.getenv("APP_BROWSER_REMOTE_CDP_LIVE_WAIT_MS", "4000")), 1)
_LIVE_BROWSER_PATH = os.getenv("APP_BROWSER_REMOTE_CDP_LIVE_BROWSER", "").strip()
_LIVE_REMOTE_HOST = os.getenv("APP_BROWSER_REMOTE_CDP_LIVE_HOST", "").strip()


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


def _non_loopback_host() -> str | None:
    if _LIVE_REMOTE_HOST:
        return _LIVE_REMOTE_HOST
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            address = probe.getsockname()[0].strip()
        if address and not address.startswith("127."):
            return address
    except OSError:
        pass
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, family=socket.AF_INET)
    except OSError:
        infos = []
    for info in infos:
        address = str(info[4][0]).strip()
        if address and not address.startswith("127."):
            return address
    return None


class _ProxyTcpServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def _build_proxy_handler() -> type[socketserver.BaseRequestHandler]:
    class _Handler(socketserver.BaseRequestHandler):
        def handle(self) -> None:
            target_host = self.server.target_host  # type: ignore[attr-defined]
            target_port = self.server.target_port  # type: ignore[attr-defined]
            upstream = socket.create_connection((target_host, target_port), timeout=5.0)
            try:
                left = threading.Thread(
                    target=self._pipe,
                    args=(self.request, upstream),
                    daemon=True,
                )
                right = threading.Thread(
                    target=self._pipe,
                    args=(upstream, self.request),
                    daemon=True,
                )
                left.start()
                right.start()
                left.join()
                right.join()
            finally:
                try:
                    upstream.close()
                except OSError:
                    pass

        @staticmethod
        def _pipe(source: socket.socket, destination: socket.socket) -> None:
            try:
                while True:
                    chunk = source.recv(65536)
                    if not chunk:
                        break
                    destination.sendall(chunk)
            except OSError:
                pass
            finally:
                for method_name in ("shutdown",):
                    method = getattr(destination, method_name, None)
                    if callable(method):
                        try:
                            method(socket.SHUT_WR)
                        except OSError:
                            pass

    return _Handler


class _CdpForwardServer:
    def __init__(self, *, listen_host: str, target_port: int) -> None:
        server = _ProxyTcpServer((listen_host, 0), _build_proxy_handler())
        server.target_host = "127.0.0.1"  # type: ignore[attr-defined]
        server.target_port = target_port  # type: ignore[attr-defined]
        self._server = server
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="browser-live-remote-cdp-forwarder",
            daemon=True,
        )

    @property
    def url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)


class _LivePageServer:
    def __init__(self) -> None:
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _build_handler())
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="browser-live-remote-cdp-page",
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
    <title>crxzipple remote cdp smoke</title>
  </head>
  <body>
    <main>
      <label for="query">Query</label>
      <input id="query" type="search" aria-label="Query Input" />
      <button
        id="submit"
        aria-label="Submit Button"
        onclick="document.getElementById('status').textContent = 'Ready';"
      >
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


@unittest.skipUnless(_LIVE_SMOKE_ENABLED, "remote-cdp live browser smoke test is disabled")
class BrowserLiveRemoteCdpSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        browser_binary = _browser_binary()
        if browser_binary is None:
            self.skipTest("No Chromium-compatible browser binary was found.")
        remote_host = _non_loopback_host()
        if remote_host is None:
            self.skipTest("No non-loopback host was found for remote-cdp live smoke.")

        self._browser_binary = browser_binary
        self._remote_host = remote_host
        self._proxy_opener = build_opener(ProxyHandler({}))
        self._env_no_proxy_before = os.environ.get("NO_PROXY")
        self._env_lower_no_proxy_before = os.environ.get("no_proxy")
        no_proxy_value = ",".join(
            part
            for part in (
                self._env_no_proxy_before or "",
                self._remote_host,
            )
            if part
        )
        os.environ["NO_PROXY"] = no_proxy_value
        os.environ["no_proxy"] = no_proxy_value
        self._page_server = _LivePageServer()
        self._page_server.start()
        self._profile_dir_context = tempfile.TemporaryDirectory(
            prefix="crxzipple-live-remote-cdp-profile-",
        )
        self._profile_dir = Path(self._profile_dir_context.name)
        self._browser_process = subprocess.Popen(
            [
                self._browser_binary,
                "--remote-debugging-address=127.0.0.1",
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
        self._remote_cdp_url = self._wait_for_cdp_ready()

        self.harness = SqliteTestHarness()
        browser_state_dir = str(Path(self.harness._tempdir.name) / "browser")
        seed_browser_state_root(
            browser_state_dir,
            default_profile="remote",
            profiles=[
                {"name": "crxzipple"},
                {
                    "name": "remote",
                    "driver": "managed",
                    "cdp_url": self._remote_cdp_url,
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
        proxy_server = getattr(self, "_cdp_forward_server", None)
        if proxy_server is not None:
            proxy_server.close()
        self._terminate_browser_process()
        self._page_server.close()
        self._profile_dir_context.cleanup()
        if self._env_no_proxy_before is None:
            os.environ.pop("NO_PROXY", None)
        else:
            os.environ["NO_PROXY"] = self._env_no_proxy_before
        if self._env_lower_no_proxy_before is None:
            os.environ.pop("no_proxy", None)
        else:
            os.environ["no_proxy"] = self._env_lower_no_proxy_before

    def test_remote_cdp_profile_snapshot_ref_and_actions_flow(self) -> None:
        profiles_response = self.client.get("/browser/profiles")
        self.assertEqual(profiles_response.status_code, 200, profiles_response.text)
        profiles_payload = profiles_response.json()
        self.assertEqual(profiles_payload["default_profile"], "remote")
        remote_profile = next(
            profile
            for profile in profiles_payload["profiles"]
            if profile["name"] == "remote"
        )
        self.assertEqual(remote_profile["mode"], "remote-cdp")
        self.assertFalse(remote_profile["supports_reset"])
        self.assertFalse(remote_profile["supports_per_tab_ws"])
        self.assertFalse(remote_profile["supports_json_tab_endpoints"])

        open_response = self.client.post(
            "/browser/control",
            json={
                "profile_name": "remote",
                "kind": "open-tab",
                "payload": {"url": self._page_server.url},
                "timeout_ms": 20_000,
            },
        )
        if open_response.status_code != 200:
            detail = open_response.text
            if "cdp" in detail.lower() or "playwright" in detail.lower():
                self.skipTest(detail)
            self.fail(f"open-tab failed: {detail}")
        open_payload = open_response.json()
        target_id = open_payload["target_id"]
        self.assertIsNone(open_payload.get("ws_url"))
        self.assertIsNone(open_payload.get("json_endpoints"))

        settle_response = self.client.post(
            "/browser/actions",
            json={
                "profile_name": "remote",
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
                "profile_name": "remote",
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
            (
                item
                for item in items
                if item.get("role") in {"textbox", "searchbox"}
                or item.get("tag") == "input"
                or "query" in str(item.get("label") or "").lower()
            ),
            None,
        )
        button_item = next(
            (
                item
                for item in items
                if item.get("role") == "button" or item.get("tag") == "button"
            ),
            None,
        )
        self.assertIsNotNone(query_item, "interactive snapshot returned no query ref")
        self.assertIsNotNone(button_item, "interactive snapshot returned no button ref")

        fill_response = self.client.post(
            "/browser/actions",
            json={
                "profile_name": "remote",
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
                "profile_name": "remote",
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
                "profile_name": "remote",
                "kind": "wait",
                "target_id": target_id,
                "payload": {
                    "expression": "document.querySelector('#status')?.textContent === 'Ready'",
                },
                "timeout_ms": 15_000,
            },
        )
        self.assertEqual(wait_ready_response.status_code, 200, wait_ready_response.text)

        title_response = self.client.post(
            "/browser/actions",
            json={
                "profile_name": "remote",
                "kind": "snapshot",
                "target_id": target_id,
                "payload": {"format": "title"},
                "timeout_ms": 15_000,
            },
        )
        self.assertEqual(title_response.status_code, 200, title_response.text)
        self.assertIn(
            "crxzipple remote cdp smoke",
            str(title_response.json()["value"]["result"]["value"]).lower(),
        )

        close_response = self.client.post(
            "/browser/control",
            json={
                "profile_name": "remote",
                "kind": "close-tab",
                "target_id": target_id,
                "timeout_ms": 10_000,
            },
        )
        self.assertEqual(close_response.status_code, 200, close_response.text)

    def _wait_for_cdp_ready(self) -> str:
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
                if not hasattr(self, "_cdp_forward_server"):
                    self._cdp_forward_server = _CdpForwardServer(
                        listen_host=self._remote_host,
                        target_port=port,
                    )
                    self._cdp_forward_server.start()
                cdp_url = self._cdp_forward_server.url
                with self._proxy_opener.open(f"{cdp_url}/json/version", timeout=1.0) as response:  # noqa: S310
                    payload = json.loads(response.read().decode("utf-8"))
                if isinstance(payload, dict) and payload.get("webSocketDebuggerUrl"):
                    return cdp_url
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
