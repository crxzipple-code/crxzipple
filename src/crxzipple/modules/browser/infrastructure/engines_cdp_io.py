from __future__ import annotations

import json
from typing import Any

import requests

from crxzipple.modules.browser.domain import (
    BrowserExecutionPlan,
    BrowserValidationError,
)

from .cdp_urls import normalize_cdp_http_base


def request_error_message(
    *,
    method: str,
    url: str,
    exc: Exception,
) -> str:
    return f"Browser CDP request {method.upper()} {url} failed: {exc}"


def read_json_response(
    *,
    method: str,
    url: str,
    response: requests.Response,
) -> Any:
    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        raise BrowserValidationError(
            request_error_message(method=method, url=url, exc=exc),
        ) from exc
    try:
        return response.json()
    except ValueError as exc:
        raise BrowserValidationError(
            f"Browser CDP request {method.upper()} {url} returned non-JSON content.",
        ) from exc


def send_cdp_command(
    *,
    ws_connect,
    ws_url: str,
    method: str,
    params: dict[str, Any] | None = None,
    timeout_s: float,
) -> None:
    request_id = 1
    try:
        socket = ws_connect(ws_url, timeout=timeout_s)
    except Exception as exc:  # noqa: BLE001
        raise BrowserValidationError(
            f"Browser CDP websocket {ws_url} could not be opened: {exc}",
        ) from exc

    try:
        socket.send(
            json.dumps(
                {
                    "id": request_id,
                    "method": method,
                    "params": dict(params or {}),
                },
            ),
        )
        while True:
            raw_message = socket.recv()
            if not isinstance(raw_message, str):
                continue
            try:
                payload = json.loads(raw_message)
            except ValueError:
                continue
            if not isinstance(payload, dict):
                continue
            if payload.get("id") != request_id:
                continue
            error = payload.get("error")
            if isinstance(error, dict):
                message = str(error.get("message") or method)
                raise BrowserValidationError(
                    f"Browser CDP command '{method}' failed: {message}",
                )
            return
    except BrowserValidationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise BrowserValidationError(
            f"Browser CDP command '{method}' failed: {exc}",
        ) from exc
    finally:
        try:
            socket.close()
        except Exception:  # noqa: BLE001
            pass


def remote_allow_origins(*, host: str, port: int) -> str:
    normalized_host = str(host).strip().lower()
    if normalized_host in {"127.0.0.1", "localhost", "::1"}:
        return ",".join(
            (
                f"http://127.0.0.1:{port}",
                f"http://localhost:{port}",
                f"http://[::1]:{port}",
            )
        )
    return f"http://{host}:{port}"


def has_expected_remote_allow_origins(
    *,
    command: str,
    host: str,
    port: int,
) -> bool:
    expected = f"--remote-allow-origins={remote_allow_origins(host=host, port=port)}"
    return expected in command


def push_cdp_base(candidates: list[str], value: object) -> None:
    try:
        normalized = normalize_cdp_http_base(value if isinstance(value, str) else None)
    except BrowserValidationError:
        return
    if normalized not in candidates:
        candidates.append(normalized)


def missing_cdp_endpoint_message(*, plan: BrowserExecutionPlan) -> str:
    if plan.profile.driver == "existing-session":
        return (
            f"Existing-session browser profile '{plan.profile.name}' requires a "
            "configured CDP URL or port. Start the target browser with remote "
            "debugging enabled and set cdp_url/cdp_port before using this profile."
        )
    if plan.capabilities.is_remote:
        return (
            f"Remote browser profile '{plan.profile.name}' requires a configured "
            "CDP URL or port."
        )
    return f"Browser profile '{plan.profile.name}' does not expose a CDP endpoint."


__all__ = [
    "has_expected_remote_allow_origins",
    "missing_cdp_endpoint_message",
    "push_cdp_base",
    "read_json_response",
    "request_error_message",
    "send_cdp_command",
]
