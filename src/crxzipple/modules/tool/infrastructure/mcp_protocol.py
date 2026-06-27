from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from crxzipple.modules.tool.domain.exceptions import ToolValidationError

from .mcp_diagnostics import redact_mcp_diagnostic

MCP_PROTOCOL_VERSION = "2024-11-05"
MCP_CLIENT_INFO = {
    "name": "crxzipple",
    "version": "0.1.0",
}


def initialize_params() -> dict[str, Any]:
    return {
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": dict(MCP_CLIENT_INFO),
    }


def jsonrpc_request_payload(method: str, params: dict[str, Any]) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": uuid4().hex,
        "method": method,
        "params": params,
    }


def jsonrpc_notification_payload(method: str, params: dict[str, Any]) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
    }


def parse_json_response(stdout: str) -> dict[str, Any]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise ToolValidationError("MCP command returned no JSON response.")

    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise ToolValidationError(
            "MCP command returned invalid JSON on stdout.",
        ) from exc

    if not isinstance(payload, dict):
        raise ToolValidationError("MCP command response must decode to a JSON object.")
    return payload


def require_result_payload(
    response: dict[str, Any],
    *,
    provider_name: str,
    method: str,
) -> dict[str, Any]:
    error = response.get("error")
    if isinstance(error, dict):
        message = str(error.get("message", "unknown MCP error"))
        raise ToolValidationError(
            "MCP provider "
            f"'{provider_name}' returned an error for method '{method}': "
            f"{redact_mcp_diagnostic(message)}",
        )

    result = response.get("result")
    if not isinstance(result, dict):
        raise ToolValidationError(
            f"MCP provider '{provider_name}' returned an invalid result payload for method '{method}'.",
        )
    return result


def require_tools_payload(result: dict[str, Any], *, provider_name: str) -> list[dict[str, Any]]:
    tools = result.get("tools")
    if not isinstance(tools, list):
        raise ToolValidationError(
            f"MCP provider '{provider_name}' returned an invalid tools/list payload.",
        )
    return [tool for tool in tools if isinstance(tool, dict)]


__all__ = [
    "MCP_PROTOCOL_VERSION",
    "initialize_params",
    "jsonrpc_notification_payload",
    "jsonrpc_request_payload",
    "parse_json_response",
    "require_result_payload",
    "require_tools_payload",
]
