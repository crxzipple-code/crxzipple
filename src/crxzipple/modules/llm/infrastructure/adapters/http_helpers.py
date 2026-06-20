from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import requests

OPENAI_TRANSIENT_HTTP_STATUS_CODES = {408, 429, 500, 502, 503, 504}
OPENAI_TRANSIENT_STREAM_MAX_ATTEMPTS = 3
OPENAI_TRANSIENT_STREAM_INITIAL_BACKOFF_SECONDS = 0.25


class RetryableOpenAIStreamError(RuntimeError):
    """Signals an upstream error that is safe to replay before output was emitted."""


def is_retryable_openai_stream_exception(exc: BaseException) -> bool:
    if isinstance(exc, RetryableOpenAIStreamError):
        return True
    return isinstance(
        exc,
        (
            requests.ConnectionError,
            requests.Timeout,
            httpx.TimeoutException,
            httpx.TransportError,
        ),
    )


def openai_stream_backoff_seconds(attempt_number: int) -> float:
    if attempt_number <= 1:
        return OPENAI_TRANSIENT_STREAM_INITIAL_BACKOFF_SECONDS
    return OPENAI_TRANSIENT_STREAM_INITIAL_BACKOFF_SECONDS * (2 ** (attempt_number - 1))


def sleep_before_openai_stream_retry(attempt_number: int) -> None:
    time.sleep(openai_stream_backoff_seconds(attempt_number))


async def async_sleep_before_openai_stream_retry(attempt_number: int) -> None:
    await asyncio.sleep(openai_stream_backoff_seconds(attempt_number))


def join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def resolve_credential_binding(
    binding_id: str | None,
    *,
    required: bool,
    description: str,
    resolved_credential: str | None = None,
) -> str | None:
    if resolved_credential is not None and resolved_credential.strip():
        return resolved_credential.strip()

    normalized_binding_id = binding_id.strip() if binding_id is not None else ""
    if normalized_binding_id:
        raise RuntimeError(
            f"{description} declares Access credential binding '{normalized_binding_id}' "
            "but no resolved credential was injected.",
        )
    if required:
        raise RuntimeError(f"{description} requires an injected resolved credential.")
    return None


def ensure_json_response(
    response: requests.Response,
    *,
    description: str,
) -> dict[str, Any]:
    if response.status_code >= 400:
        raise RuntimeError(
            f"{description} failed with HTTP {response.status_code}: {response.text}",
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"{description} returned invalid JSON: {response.text}",
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{description} returned a non-object JSON payload.")
    return payload


async def httpx_response_text(response: httpx.Response) -> str:
    try:
        return response.text
    except httpx.ResponseNotRead:
        body = await response.aread()
        return body.decode("utf-8", errors="replace")


async def ensure_async_json_response(
    response: httpx.Response,
    *,
    description: str,
) -> dict[str, Any]:
    response_text = await httpx_response_text(response)
    if response.status_code >= 400:
        raise RuntimeError(
            f"{description} failed with HTTP {response.status_code}: {response_text}",
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"{description} returned invalid JSON: {response_text}",
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{description} returned a non-object JSON payload.")
    return payload
