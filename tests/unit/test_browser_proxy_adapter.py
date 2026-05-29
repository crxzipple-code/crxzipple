from __future__ import annotations

import base64
import socket
import socketserver
import threading
import unittest

from crxzipple.modules.browser.domain import BrowserValidationError
from crxzipple.modules.browser.infrastructure.proxy_adapter import (
    BrowserLocalProxyAdapter,
    normalize_upstream_proxy_endpoint,
    parse_basic_proxy_credential,
    parse_bearer_proxy_credential,
)


class _ThreadingServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class _UpstreamProxyHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = self.request.recv(4096)
            if not chunk:
                break
            data += chunk
        self.server.requests.append(data.decode("latin-1"))  # type: ignore[attr-defined]
        self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")


class BrowserProxyAdapterTestCase(unittest.TestCase):
    def test_local_proxy_adapter_injects_basic_auth_without_exposing_secret_in_url(self) -> None:
        upstream = _ThreadingServer(("127.0.0.1", 0), _UpstreamProxyHandler)
        upstream.requests = []  # type: ignore[attr-defined]
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        adapter = BrowserLocalProxyAdapter(
            upstream_proxy_url=f"http://127.0.0.1:{upstream.server_address[1]}",
            credential='{"username":"proxy-user","password":"proxy-secret"}',
        )
        try:
            local_url = adapter.start()
            self.assertIn("127.0.0.1", local_url)
            self.assertNotIn("proxy-user", local_url)
            self.assertNotIn("proxy-secret", local_url)

            host, port_text = local_url.removeprefix("http://").split(":", 1)
            with socket.create_connection((host, int(port_text)), timeout=2.0) as sock:
                sock.sendall(
                    b"CONNECT example.com:443 HTTP/1.1\r\n"
                    b"Host: example.com:443\r\n"
                    b"\r\n",
                )
                response = sock.recv(4096)

            self.assertIn(b"200 Connection Established", response)
            self.assertEqual(len(upstream.requests), 1)  # type: ignore[attr-defined]
            request = upstream.requests[0]  # type: ignore[attr-defined]
            expected = base64.b64encode(b"proxy-user:proxy-secret").decode("ascii")
            self.assertIn(f"Proxy-Authorization: Basic {expected}", request)
        finally:
            adapter.close()
            upstream.shutdown()
            upstream.server_close()
            thread.join(timeout=1.0)

    def test_proxy_credential_accepts_basic_header_and_user_password_json(self) -> None:
        basic = base64.b64encode(b"alice:secret").decode("ascii")
        parsed = parse_basic_proxy_credential(f"Basic {basic}")

        self.assertEqual(parsed.username, "alice")
        self.assertEqual(parsed.password, "secret")
        self.assertEqual(
            parse_basic_proxy_credential('{"user":"bob","pass":"hidden"}').username,
            "bob",
        )

    def test_local_proxy_adapter_injects_bearer_auth(self) -> None:
        upstream = _ThreadingServer(("127.0.0.1", 0), _UpstreamProxyHandler)
        upstream.requests = []  # type: ignore[attr-defined]
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        adapter = BrowserLocalProxyAdapter(
            upstream_proxy_url=f"http://127.0.0.1:{upstream.server_address[1]}",
            credential='{"access_token":"proxy-token"}',
            credential_kind="bearer_token",
        )
        try:
            local_url = adapter.start()
            host, port_text = local_url.removeprefix("http://").split(":", 1)
            with socket.create_connection((host, int(port_text)), timeout=2.0) as sock:
                sock.sendall(
                    b"CONNECT example.com:443 HTTP/1.1\r\n"
                    b"Host: example.com:443\r\n"
                    b"\r\n",
                )
                response = sock.recv(4096)

            self.assertIn(b"200 Connection Established", response)
            request = upstream.requests[0]  # type: ignore[attr-defined]
            self.assertIn("Proxy-Authorization: Bearer proxy-token", request)
            self.assertEqual(parse_bearer_proxy_credential("Bearer abc").token, "abc")
        finally:
            adapter.close()
            upstream.shutdown()
            upstream.server_close()
            thread.join(timeout=1.0)

    def test_authenticated_proxy_endpoint_rejects_socks_and_embedded_credentials(self) -> None:
        with self.assertRaisesRegex(BrowserValidationError, "http:// or https://"):
            normalize_upstream_proxy_endpoint("socks5://127.0.0.1:7890")
        with self.assertRaisesRegex(BrowserValidationError, "must not contain credentials"):
            normalize_upstream_proxy_endpoint("http://user:pass@example.com:8080")


if __name__ == "__main__":
    unittest.main()
