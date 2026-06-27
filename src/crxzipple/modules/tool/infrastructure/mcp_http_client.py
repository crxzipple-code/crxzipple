from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

from crxzipple.core.config import McpProviderSettings
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.shared.http import request_url

from .mcp_diagnostics import redact_mcp_diagnostic
from .mcp_protocol import (
    MCP_PROTOCOL_VERSION,
    initialize_params,
    jsonrpc_notification_payload,
    jsonrpc_request_payload,
    require_result_payload,
    require_tools_payload,
)


class McpHttpClient:
    def __init__(self, config: McpProviderSettings) -> None:
        self.config = config
        self._lock = threading.Lock()
        self._initialized = False
        self._session_id: str | None = None

    def list_tools(self) -> list[dict[str, Any]]:
        result = self.request("tools/list")
        return require_tools_payload(result, provider_name=self.config.name)

    def call_tool(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        return self.request(
            "tools/call",
            {
                "name": tool_name,
                "arguments": dict(arguments),
            },
        )

    async def call_tool_async(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        return await asyncio.to_thread(
            self.call_tool,
            tool_name=tool_name,
            arguments=arguments,
        )

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._ensure_session_locked()
            return self._request_locked(method, params or {})

    def close(self) -> None:
        with self._lock:
            self._initialized = False
            self._session_id = None

    def _ensure_session_locked(self) -> None:
        if self._initialized:
            return
        self._request_locked(
            "initialize",
            initialize_params(),
            initialize_request=True,
        )
        self._send_notification_locked("notifications/initialized", {})
        self._initialized = True

    def _request_locked(
        self,
        method: str,
        params: dict[str, Any],
        *,
        initialize_request: bool = False,
    ) -> dict[str, Any]:
        endpoint_url = self.config.endpoint_url
        if endpoint_url is None:
            raise ToolValidationError(
                f"MCP provider '{self.config.name}' HTTP endpoint is not configured.",
            )
        payload = jsonrpc_request_payload(method, params)
        response_payload = self._post_json_locked(endpoint_url, payload)
        if initialize_request:
            self._capture_session_id(response_payload)
        return require_result_payload(
            response_payload,
            provider_name=self.config.name,
            method=method,
        )

    def _send_notification_locked(
        self,
        method: str,
        params: dict[str, Any],
    ) -> None:
        endpoint_url = self.config.endpoint_url
        if endpoint_url is None:
            return
        payload = jsonrpc_notification_payload(method, params)
        self._post_json_locked(endpoint_url, payload, expect_response=False)

    def _post_json_locked(
        self,
        endpoint_url: str,
        payload: dict[str, Any],
        *,
        expect_response: bool = True,
    ) -> dict[str, Any]:
        try:
            response = request_url(
                "POST",
                endpoint_url,
                json=payload,
                headers=self._headers(),
                timeout=max(float(self.config.timeout_seconds), 1.0),
            )
            if response.status_code == 202 and not expect_response:
                self._capture_session_id_from_headers(response.headers)
                return {}
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            raise ToolValidationError(
                "MCP provider "
                f"'{self.config.name}' HTTP request failed: {redact_mcp_diagnostic(exc)}",
            ) from exc
        self._capture_session_id_from_headers(response.headers)
        if not expect_response and not response.text.strip():
            return {}
        return self._decode_response_payload(response.text)

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
        }
        if self._session_id is not None:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    def _capture_session_id(self, response_payload: dict[str, Any]) -> None:
        session_id = response_payload.get("sessionId")
        if isinstance(session_id, str) and session_id.strip():
            self._session_id = session_id.strip()

    def _capture_session_id_from_headers(self, headers: Any) -> None:
        for key in ("Mcp-Session-Id", "mcp-session-id", "MCP-Session-Id"):
            value = headers.get(key) if hasattr(headers, "get") else None
            if isinstance(value, str) and value.strip():
                self._session_id = value.strip()
                return

    def _decode_response_payload(self, text: str) -> dict[str, Any]:
        stripped = text.strip()
        if not stripped:
            return {}
        if stripped.startswith("data:") or "\ndata:" in stripped:
            return self._decode_sse_response(stripped)
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ToolValidationError(
                f"MCP provider '{self.config.name}' returned non-JSON HTTP payload.",
            ) from exc
        if not isinstance(payload, dict):
            raise ToolValidationError(
                f"MCP provider '{self.config.name}' returned an invalid HTTP payload.",
            )
        return payload

    def _decode_sse_response(self, text: str) -> dict[str, Any]:
        data_lines: list[str] = []
        for line in text.splitlines():
            if line.startswith("data:"):
                data_lines.append(line.removeprefix("data:").strip())
        if not data_lines:
            raise ToolValidationError(
                f"MCP provider '{self.config.name}' returned an empty SSE payload.",
            )
        try:
            payload = json.loads("\n".join(data_lines))
        except json.JSONDecodeError as exc:
            raise ToolValidationError(
                f"MCP provider '{self.config.name}' returned invalid SSE JSON payload.",
            ) from exc
        if not isinstance(payload, dict):
            raise ToolValidationError(
                f"MCP provider '{self.config.name}' returned an invalid SSE payload.",
            )
        return payload


__all__ = ["McpHttpClient"]
