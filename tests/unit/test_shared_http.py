from __future__ import annotations

import asyncio
import unittest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from crxzipple.shared.infrastructure.http import (
    AsyncHttpClientPool,
    install_json_exception_handler,
    is_loopback_http_url,
    request_url,
)


class _FakeAsyncHttpClient:
    instances: list["_FakeAsyncHttpClient"] = []

    def __init__(self, **kwargs) -> None:  # noqa: ANN003
        self.kwargs = dict(kwargs)
        self.is_closed = False
        type(self).instances.append(self)

    async def aclose(self) -> None:
        self.is_closed = True


class _ClosedLoopAsyncHttpClient:
    instances: list["_ClosedLoopAsyncHttpClient"] = []

    def __init__(self, **kwargs) -> None:  # noqa: ANN003
        del kwargs
        self.loop = asyncio.get_running_loop()
        self.is_closed = False
        self.close_attempted = False
        type(self).instances.append(self)

    async def aclose(self) -> None:
        self.close_attempted = True
        if self.loop.is_closed():
            raise RuntimeError("Event loop is closed")
        self.is_closed = True


class SharedHttpTestCase(unittest.TestCase):
    def test_unhandled_http_exception_returns_json_envelope(self) -> None:
        app = FastAPI()
        install_json_exception_handler(app)

        @app.middleware("http")
        async def rethrowing_middleware(request, call_next):  # noqa: ANN001
            try:
                return await call_next(request)
            except Exception:
                raise

        @app.get("/boom")
        def boom() -> None:
            raise RuntimeError("database password leaked into exception text")

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/boom")

        self.assertEqual(response.status_code, 500)
        self.assertIn("application/json", response.headers["content-type"])
        self.assertEqual(
            response.json(),
            {
                "code": "internal_server_error",
                "message": "Internal server error.",
                "retryable": True,
            },
        )
        self.assertNotEqual(response.text, "Internal Server Error")
        self.assertNotIn("database password", response.text)

    def test_http_exception_response_is_not_wrapped_by_json_envelope(self) -> None:
        app = FastAPI()
        install_json_exception_handler(app)

        @app.get("/missing")
        def missing() -> None:
            raise HTTPException(status_code=404, detail="Run was not found.")

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/missing")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Run was not found."})

    def test_validation_error_response_is_not_wrapped_by_json_envelope(self) -> None:
        app = FastAPI()
        install_json_exception_handler(app)

        @app.get("/items")
        def items(limit: int) -> dict[str, int]:
            return {"limit": limit}

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/items?limit=abc")

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertIsInstance(payload["detail"], list)
        self.assertNotIn("code", payload)

    def test_is_loopback_http_url_identifies_local_hosts(self) -> None:
        self.assertTrue(is_loopback_http_url("http://127.0.0.1:4723/status"))
        self.assertTrue(is_loopback_http_url("http://localhost:4723/status"))
        self.assertFalse(is_loopback_http_url("https://example.com"))

    def test_request_url_uses_proxy_free_session_for_loopback(self) -> None:
        fake_response = object()
        fake_session = MagicMock()
        fake_session.request.return_value = fake_response

        session_factory = MagicMock()
        session_factory.__enter__.return_value = fake_session
        session_factory.__exit__.return_value = False

        with patch("requests.Session", return_value=session_factory) as patched_session:
            response = request_url("GET", "http://127.0.0.1:4723/status", timeout=5)

        self.assertIs(response, fake_response)
        patched_session.assert_called_once()
        self.assertFalse(fake_session.trust_env)
        fake_session.request.assert_called_once_with(
            "GET",
            "http://127.0.0.1:4723/status",
            timeout=5,
        )

    def test_request_url_uses_regular_requests_for_non_loopback(self) -> None:
        fake_response = object()
        with patch("requests.request", return_value=fake_response) as patched_request:
            response = request_url("GET", "https://example.com/health", timeout=5)

        self.assertIs(response, fake_response)
        patched_request.assert_called_once_with("GET", "https://example.com/health", timeout=5)

    def test_async_http_client_pool_reuses_clients_by_origin_and_timeout(self) -> None:
        _FakeAsyncHttpClient.instances = []
        pool = AsyncHttpClientPool()

        async def exercise_pool() -> None:
            first = pool.get_client(
                "https://api.example.com/v1/messages",
                timeout=30,
                client_factory=_FakeAsyncHttpClient,
            )
            second = pool.get_client(
                "https://api.example.com/v1/responses",
                timeout=30,
                client_factory=_FakeAsyncHttpClient,
            )
            third = pool.get_client(
                "https://api.example.com/v1/responses",
                timeout=60,
                client_factory=_FakeAsyncHttpClient,
            )

            self.assertIs(first, second)
            self.assertIsNot(first, third)
            self.assertEqual(first.kwargs["timeout"], 30.0)
            self.assertTrue(first.kwargs["trust_env"])
            await pool.aclose()

        asyncio.run(exercise_pool())

        self.assertEqual(len(_FakeAsyncHttpClient.instances), 2)
        self.assertTrue(all(client.is_closed for client in _FakeAsyncHttpClient.instances))

    def test_async_http_client_pool_disables_proxy_env_for_loopback(self) -> None:
        _FakeAsyncHttpClient.instances = []
        pool = AsyncHttpClientPool()

        async def exercise_pool() -> None:
            client = pool.get_client(
                "http://127.0.0.1:8000/status",
                timeout=5,
                client_factory=_FakeAsyncHttpClient,
            )
            self.assertFalse(client.kwargs["trust_env"])
            await pool.aclose()

        asyncio.run(exercise_pool())

    def test_async_http_client_pool_ignores_clients_left_on_closed_loop(self) -> None:
        _ClosedLoopAsyncHttpClient.instances = []
        pool = AsyncHttpClientPool()

        async def create_client_without_closing() -> None:
            pool.get_client(
                "https://api.example.com/v1/messages",
                timeout=30,
                client_factory=_ClosedLoopAsyncHttpClient,
            )

        asyncio.run(create_client_without_closing())
        asyncio.run(pool.aclose())

        self.assertEqual(len(_ClosedLoopAsyncHttpClient.instances), 1)
        self.assertTrue(_ClosedLoopAsyncHttpClient.instances[0].close_attempted)
