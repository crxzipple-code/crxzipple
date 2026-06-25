from __future__ import annotations

import errno
import threading
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import websocket

from crxzipple.modules.llm.infrastructure.adapters.http_helpers import (
    is_retryable_openai_stream_exception,
)


class CodexWebsocketPool:
    def __init__(self) -> None:
        self._pool: dict[tuple[str, tuple[str, ...], int], list[Any]] = {}
        self._lock = threading.Lock()

    def close_all(self) -> None:
        with self._lock:
            sockets = [ws for bucket in self._pool.values() for ws in bucket]
            self._pool.clear()
        for ws in sockets:
            close_codex_websocket(ws)

    def acquire(
        self,
        endpoint: str,
        *,
        headers: list[str],
        timeout_seconds: int,
    ) -> tuple[Any, tuple[str, tuple[str, ...], int], bool]:
        key = (endpoint, tuple(headers), timeout_seconds)
        with self._lock:
            bucket = self._pool.get(key)
            while bucket:
                ws = bucket.pop()
                if not codex_websocket_is_closed(ws):
                    return ws, key, True
        return (
            websocket.create_connection(
                endpoint,
                header=headers,
                timeout=timeout_seconds,
            ),
            key,
            False,
        )

    def release(
        self,
        key: tuple[str, tuple[str, ...], int],
        ws: Any,
    ) -> None:
        if codex_websocket_is_closed(ws):
            return
        with self._lock:
            self._pool.setdefault(key, []).append(ws)


def is_retryable_codex_websocket_exception(exc: BaseException) -> bool:
    if is_retryable_openai_stream_exception(exc):
        return True
    if isinstance(
        exc,
        (
            BrokenPipeError,
            ConnectionAbortedError,
            ConnectionResetError,
            TimeoutError,
        ),
    ):
        return True
    if isinstance(exc, OSError):
        return exc.errno in {
            errno.EPIPE,
            errno.ECONNABORTED,
            errno.ECONNRESET,
            errno.ETIMEDOUT,
        }
    websocket_exception = getattr(websocket, "WebSocketException", None)
    return isinstance(websocket_exception, type) and isinstance(exc, websocket_exception)


def codex_websocket_is_closed(ws: Any) -> bool:
    closed = getattr(ws, "closed", None)
    if isinstance(closed, bool):
        return closed
    connected = getattr(ws, "connected", None)
    if isinstance(connected, bool):
        return not connected
    sock = getattr(ws, "sock", None)
    if sock is not None:
        sock_connected = getattr(sock, "connected", None)
        if isinstance(sock_connected, bool):
            return not sock_connected
    return False


def close_codex_websocket(ws: Any) -> None:
    close = getattr(ws, "close", None)
    if callable(close):
        close()


def codex_websocket_endpoint(http_endpoint: str) -> str:
    parsed = urlsplit(http_endpoint)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunsplit((scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment))


def codex_websocket_headers(token: str | None) -> list[str]:
    headers = [
        "OpenAI-Beta: responses_websockets=2026-02-06",
        "Content-Type: application/json",
    ]
    if token is not None:
        headers.append(f"Authorization: Bearer {token}")
    return headers
