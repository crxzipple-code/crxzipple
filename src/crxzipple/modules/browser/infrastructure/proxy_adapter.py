from __future__ import annotations

from dataclasses import dataclass, field
import base64
import json
import select
import socket
import socketserver
import ssl
import threading
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests

from crxzipple.modules.browser.domain import BrowserValidationError


_MAX_HEADER_BYTES = 256 * 1024


@dataclass(frozen=True, slots=True)
class BasicProxyCredential:
    username: str
    password: str

    @property
    def authorization_header(self) -> str:
        encoded = base64.b64encode(
            f"{self.username}:{self.password}".encode("utf-8"),
        ).decode("ascii")
        return f"Basic {encoded}"


@dataclass(frozen=True, slots=True)
class BearerProxyCredential:
    token: str

    @property
    def authorization_header(self) -> str:
        return f"Bearer {self.token}"


@dataclass(frozen=True, slots=True)
class ProxyEndpoint:
    server_url: str
    scheme: str
    host: str
    port: int


def parse_basic_proxy_credential(value: str) -> BasicProxyCredential:
    raw = value.strip()
    if not raw:
        raise BrowserValidationError("Browser proxy credential is empty.")
    if raw.lower().startswith("basic "):
        try:
            decoded = base64.b64decode(raw.split(" ", 1)[1].strip()).decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            raise BrowserValidationError("Browser proxy basic credential is invalid.") from exc
        raw = decoded
    elif raw.startswith("{"):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BrowserValidationError("Browser proxy credential JSON is invalid.") from exc
        if not isinstance(payload, dict):
            raise BrowserValidationError("Browser proxy credential JSON must be an object.")
        username = str(payload.get("username") or payload.get("user") or "").strip()
        password = str(payload.get("password") or payload.get("pass") or "").strip()
        if not username or not password:
            raise BrowserValidationError(
                "Browser proxy credential JSON must contain username and password.",
            )
        return BasicProxyCredential(username=username, password=password)

    username, separator, password = raw.partition(":")
    if not separator or not username.strip() or not password:
        raise BrowserValidationError(
            "Browser proxy basic credential must be 'username:password' or JSON with username/password.",
        )
    return BasicProxyCredential(username=username.strip(), password=password)


def parse_bearer_proxy_credential(value: str) -> BearerProxyCredential:
    raw = value.strip()
    if not raw:
        raise BrowserValidationError("Browser proxy bearer credential is empty.")
    if raw.lower().startswith("bearer "):
        raw = raw.split(" ", 1)[1].strip()
    elif raw.startswith("{"):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BrowserValidationError("Browser proxy bearer credential JSON is invalid.") from exc
        if not isinstance(payload, dict):
            raise BrowserValidationError("Browser proxy bearer credential JSON must be an object.")
        raw = str(
            payload.get("token")
            or payload.get("access_token")
            or payload.get("bearer_token")
            or "",
        ).strip()
    if not raw:
        raise BrowserValidationError("Browser proxy bearer credential token is empty.")
    return BearerProxyCredential(token=raw)


def parse_proxy_credential(
    value: str,
    *,
    credential_kind: str = "basic",
) -> BasicProxyCredential | BearerProxyCredential:
    normalized_kind = credential_kind.strip().lower()
    if normalized_kind == "bearer":
        normalized_kind = "bearer_token"
    if normalized_kind == "basic":
        return parse_basic_proxy_credential(value)
    if normalized_kind == "bearer_token":
        return parse_bearer_proxy_credential(value)
    raise BrowserValidationError(
        "Browser proxy credential kind must be one of: basic, bearer_token.",
    )


def normalize_upstream_proxy_endpoint(server_url: str) -> ProxyEndpoint:
    raw = server_url.strip()
    if not raw:
        raise BrowserValidationError("Browser proxy server URL is required.")
    parsed = urlsplit(raw)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise BrowserValidationError(
            "Authenticated browser proxy supports http:// or https:// upstream proxy URLs.",
        )
    if parsed.username or parsed.password:
        raise BrowserValidationError(
            "Browser proxy server URL must not contain credentials.",
        )
    if not parsed.hostname:
        raise BrowserValidationError("Browser proxy server URL must include a host.")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise BrowserValidationError(
            "Browser proxy server URL must not include path, query, or fragment.",
        )
    default_port = 443 if scheme == "https" else 80
    port = parsed.port or default_port
    netloc = f"{parsed.hostname}:{port}"
    return ProxyEndpoint(
        server_url=urlunsplit((scheme, netloc, "", "", "")),
        scheme=scheme,
        host=parsed.hostname,
        port=port,
    )


class _ThreadingProxyServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class _ProxyRequestHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        self.server.adapter.handle_client(self.request)  # type: ignore[attr-defined]


@dataclass(slots=True)
class BrowserLocalProxyAdapter:
    """Local HTTP proxy that injects Access-managed auth upstream."""

    upstream_proxy_url: str
    credential: str
    credential_kind: str = "basic"
    bind_host: str = "127.0.0.1"
    connect_timeout_s: float = 10.0
    _endpoint: ProxyEndpoint = field(init=False, repr=False)
    _credential: BasicProxyCredential | BearerProxyCredential = field(init=False, repr=False)
    _server: _ThreadingProxyServer | None = field(default=None, init=False, repr=False)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        credential_kind = self.credential_kind.strip().lower()
        if credential_kind == "bearer":
            credential_kind = "bearer_token"
        object.__setattr__(self, "credential_kind", credential_kind)
        object.__setattr__(
            self,
            "_endpoint",
            normalize_upstream_proxy_endpoint(self.upstream_proxy_url),
        )
        object.__setattr__(
            self,
            "_credential",
            parse_proxy_credential(
                self.credential,
                credential_kind=self.credential_kind,
            ),
        )

    @property
    def server_url(self) -> str:
        server = self._server
        if server is None:
            raise BrowserValidationError("Browser local proxy adapter has not started.")
        host, port = server.server_address
        return f"http://{host}:{port}"

    def start(self) -> str:
        if self._server is None:
            server = _ThreadingProxyServer((self.bind_host, 0), _ProxyRequestHandler)
            server.adapter = self  # type: ignore[attr-defined]
            thread = threading.Thread(
                target=server.serve_forever,
                name="browser-local-proxy-adapter",
                daemon=True,
            )
            thread.start()
            self._server = server
            self._thread = thread
        return self.server_url

    def close(self) -> None:
        server = self._server
        self._server = None
        if server is not None:
            server.shutdown()
            server.server_close()
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)

    def metadata(self) -> dict[str, str | int]:
        endpoint = self._endpoint
        return {
            "proxy_adapter": "local_http_authenticated",
            "proxy_upstream": endpoint.server_url,
            "proxy_credential_kind": self.credential_kind,
            "proxy_upstream_scheme": endpoint.scheme,
            "proxy_upstream_host": endpoint.host,
            "proxy_upstream_port": endpoint.port,
            "proxy_local_url": self.server_url,
        }

    def check_egress(self, url: str, *, timeout_s: float = 5.0) -> dict[str, Any]:
        session = requests.Session()
        session.trust_env = False
        try:
            response = session.get(
                url,
                proxies={"http": self.server_url, "https": self.server_url},
                timeout=timeout_s,
            )
            response.raise_for_status()
            return {
                "status": "ready",
                "ip": _extract_ipish_value(response),
                "url": url,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "failed",
                "reason": str(exc),
                "url": url,
            }
        finally:
            session.close()

    def handle_client(self, client: socket.socket) -> None:
        client.settimeout(self.connect_timeout_s)
        try:
            first_line, headers, buffered = _read_http_header(client)
            parts = first_line.split()
            if len(parts) < 3:
                return
            method = parts[0].upper()
            if method == "CONNECT":
                self._handle_connect(client, target=parts[1])
            else:
                self._handle_forward(client, first_line=first_line, headers=headers, buffered=buffered)
        except OSError:
            return

    def _handle_connect(self, client: socket.socket, *, target: str) -> None:
        upstream = self._open_upstream()
        try:
            request = (
                f"CONNECT {target} HTTP/1.1\r\n"
                f"Host: {target}\r\n"
                "Proxy-Connection: Keep-Alive\r\n"
                f"Proxy-Authorization: {self._credential.authorization_header}\r\n"
                "\r\n"
            ).encode("latin-1")
            upstream.sendall(request)
            response = _read_raw_header(upstream)
            client.sendall(response)
            status_line = response.split(b"\r\n", 1)[0].decode("latin-1", errors="replace")
            if " 200 " in status_line or status_line.endswith(" 200"):
                _tunnel(client, upstream)
        finally:
            upstream.close()

    def _handle_forward(
        self,
        client: socket.socket,
        *,
        first_line: str,
        headers: list[tuple[str, str]],
        buffered: bytes,
    ) -> None:
        upstream = self._open_upstream()
        try:
            upstream.sendall(
                _rewrite_forward_headers(
                    first_line=first_line,
                    headers=headers,
                    authorization_header=self._credential.authorization_header,
                ),
            )
            if buffered:
                upstream.sendall(buffered)
            _tunnel(client, upstream)
        finally:
            upstream.close()

    def _open_upstream(self) -> socket.socket:
        endpoint = self._endpoint
        raw = socket.create_connection(
            (endpoint.host, endpoint.port),
            timeout=self.connect_timeout_s,
        )
        if endpoint.scheme == "https":
            return ssl.create_default_context().wrap_socket(
                raw,
                server_hostname=endpoint.host,
            )
        return raw


def _read_http_header(client: socket.socket) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = _read_raw_header(client)
    header_bytes, _, buffered = raw.partition(b"\r\n\r\n")
    lines = header_bytes.decode("latin-1", errors="replace").split("\r\n")
    first_line = lines[0]
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        name, separator, value = line.partition(":")
        if not separator:
            continue
        headers.append((name.strip(), value.strip()))
    return first_line, headers, buffered


def _read_raw_header(sock: socket.socket) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > _MAX_HEADER_BYTES:
            raise OSError("HTTP header is too large.")
        data = b"".join(chunks)
        if b"\r\n\r\n" in data:
            return data
    return b"".join(chunks)


def _rewrite_forward_headers(
    *,
    first_line: str,
    headers: list[tuple[str, str]],
    authorization_header: str,
) -> bytes:
    rewritten = [first_line]
    for name, value in headers:
        if name.lower() in {"proxy-authorization", "proxy-connection"}:
            continue
        rewritten.append(f"{name}: {value}")
    rewritten.append("Proxy-Connection: Keep-Alive")
    rewritten.append(f"Proxy-Authorization: {authorization_header}")
    rewritten.append("")
    rewritten.append("")
    return "\r\n".join(rewritten).encode("latin-1")


def _tunnel(left: socket.socket, right: socket.socket) -> None:
    sockets = [left, right]
    for item in sockets:
        item.setblocking(False)
    try:
        while True:
            readable, _, exceptional = select.select(sockets, (), sockets, 1.0)
            if exceptional:
                return
            if not readable:
                continue
            for source in readable:
                try:
                    data = source.recv(8192)
                except BlockingIOError:
                    continue
                if not data:
                    return
                target = right if source is left else left
                target.sendall(data)
    finally:
        for item in sockets:
            try:
                item.setblocking(True)
            except OSError:
                pass


def _extract_ipish_value(response: requests.Response) -> str:
    content_type = response.headers.get("content-type", "")
    if "json" in content_type.lower():
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            value = payload.get("ip") or payload.get("origin") or payload.get("query")
            if isinstance(value, str) and value.strip():
                return value.strip()
    text = response.text.strip()
    return text[:120] if text else "-"
