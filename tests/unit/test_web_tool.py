from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

import tools.web.local as web_local


class _FakeResponse:
    def __init__(
        self,
        *,
        url: str = "https://example.com/latest",
        status_code: int = 200,
        reason: str = "OK",
        headers: dict[str, str] | None = None,
        body: bytes = b"",
    ) -> None:
        self.url = url
        self.status_code = status_code
        self.reason = reason
        self.headers = dict(headers or {})
        self._body = body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def iter_content(self, *, chunk_size: int) -> Any:
        for index in range(0, len(self._body), chunk_size):
            yield self._body[index:index + chunk_size]


def test_web_fetch_json_extracts_json_path(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "base_code": "USD",
        "rates": {
            "JPY": 160.279502,
        },
        "time_last_update_utc": "Wed, 10 Jun 2026 00:02:31 +0000",
    }

    def fake_get(*_args: object, **_kwargs: object) -> _FakeResponse:
        return _FakeResponse(
            headers={"Content-Type": "application/json; charset=utf-8"},
            body=json.dumps(payload).encode("utf-8"),
        )

    monkeypatch.setattr(web_local, "_validate_public_url", lambda _url: None)
    monkeypatch.setattr(web_local.requests, "get", fake_get)

    result = asyncio.run(
        web_local.fetch_json(None)(
            {
                "url": "https://example.com/latest/USD",
                "json_path": "rates.JPY",
            },
        ),
    )

    assert result.metadata["tool"] == "web.fetch_json"
    assert result.metadata["json_path_found"] is True
    assert result.details["json_path_value"] == 160.279502
    assert "JSON path rates.JPY: 160.279502" in result.blocks[0]["text"]


def test_web_fetch_rejects_localhost() -> None:
    with pytest.raises(ValueError, match="localhost"):
        asyncio.run(
            web_local.fetch_json(None)(
                {
                    "url": "http://localhost:8000/secret",
                },
            ),
        )


def test_public_hostname_resolved_to_benchmark_proxy_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        web_local.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (
                web_local.socket.AF_INET,
                web_local.socket.SOCK_STREAM,
                6,
                "",
                ("198.18.0.32", 443),
            ),
        ],
    )

    web_local._validate_public_url("https://open.example.test/data.json")


def test_literal_benchmark_proxy_ip_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-public address 198.18.0.32"):
        web_local._validate_public_url("https://198.18.0.32/data.json")
