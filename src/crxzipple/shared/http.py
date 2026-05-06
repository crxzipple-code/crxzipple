from __future__ import annotations

import asyncio
from collections.abc import Callable
import ipaddress
import logging
from typing import Any
from urllib.parse import urlparse
from weakref import WeakKeyDictionary

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import httpx
import requests


AsyncHttpClientFactory = Callable[..., httpx.AsyncClient]
HttpErrorLogger = logging.Logger | logging.LoggerAdapter[Any]


def install_json_exception_handler(
    app: FastAPI,
    *,
    logger: HttpErrorLogger | None = None,
) -> None:
    @app.exception_handler(Exception)
    async def handle_unhandled_exception(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        if logger is not None:
            logger.exception(
                "unhandled HTTP exception",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                },
                exc_info=True,
            )
        return JSONResponse(
            status_code=500,
            content={
                "code": "internal_server_error",
                "message": "Internal server error.",
                "retryable": True,
            },
        )


def is_loopback_http_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        return False
    if hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def request_url(method: str, url: str, **kwargs) -> requests.Response:  # noqa: ANN003
    if is_loopback_http_url(url):
        with requests.Session() as session:
            session.trust_env = False
            return session.request(method, url, **kwargs)
    return requests.request(method, url, **kwargs)


class AsyncHttpClientPool:
    def __init__(self) -> None:
        self._clients: WeakKeyDictionary[
            asyncio.AbstractEventLoop,
            dict[tuple[str, float | None, bool, int], httpx.AsyncClient],
        ] = WeakKeyDictionary()

    def get_client(
        self,
        url: str,
        *,
        timeout: float | int | None = None,
        client_factory: AsyncHttpClientFactory = httpx.AsyncClient,
    ) -> httpx.AsyncClient:
        loop = asyncio.get_running_loop()
        origin = _http_origin(url)
        timeout_value = float(timeout) if timeout is not None else None
        trust_env = not is_loopback_http_url(url)
        key = (origin, timeout_value, trust_env, id(client_factory))
        clients_by_key = self._clients.setdefault(loop, {})
        client = clients_by_key.get(key)
        if client is not None and not _is_async_client_closed(client):
            return client

        client = client_factory(
            timeout=timeout_value,
            trust_env=trust_env,
        )
        clients_by_key[key] = client
        return client

    async def aclose(self) -> None:
        clients: list[httpx.AsyncClient] = []
        for clients_by_key in list(self._clients.values()):
            clients.extend(clients_by_key.values())
            clients_by_key.clear()
        self._clients.clear()

        await _close_async_clients(clients)


_DEFAULT_ASYNC_HTTP_CLIENT_POOL = AsyncHttpClientPool()


def get_async_http_client(
    url: str,
    *,
    timeout: float | int | None = None,
    client_factory: AsyncHttpClientFactory = httpx.AsyncClient,
) -> httpx.AsyncClient:
    return _DEFAULT_ASYNC_HTTP_CLIENT_POOL.get_client(
        url,
        timeout=timeout,
        client_factory=client_factory,
    )


async def close_async_http_clients() -> None:
    await _DEFAULT_ASYNC_HTTP_CLIENT_POOL.aclose()


def close_async_http_clients_sync() -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(close_async_http_clients())
        return
    loop.create_task(close_async_http_clients())


def _http_origin(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    if not scheme or not hostname:
        return url
    port = parsed.port
    if port is None:
        return f"{scheme}://{hostname}"
    return f"{scheme}://{hostname}:{port}"


def _is_async_client_closed(client: Any) -> bool:
    return bool(getattr(client, "is_closed", False))


async def _close_async_clients(clients: list[httpx.AsyncClient]) -> None:
    for client in clients:
        aclose = getattr(client, "aclose", None)
        if not callable(aclose) or _is_async_client_closed(client):
            continue
        try:
            await aclose()
        except RuntimeError as exc:
            if "Event loop is closed" not in str(exc):
                raise
