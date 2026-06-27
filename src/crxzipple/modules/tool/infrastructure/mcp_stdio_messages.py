from __future__ import annotations

import json
from typing import Any

from crxzipple.modules.tool.domain.exceptions import ToolValidationError

from .mcp_diagnostics import redact_mcp_diagnostic
from .mcp_protocol import parse_json_response


def stdio_message_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload) + "\n"


def stdio_message_bytes(payload: dict[str, Any]) -> bytes:
    return stdio_message_text(payload).encode("utf-8")


def parse_stdio_response_line(
    line: str,
    *,
    expected_id: str,
    provider_name: str,
    method: str,
) -> dict[str, Any] | None:
    response = parse_json_response(line)
    response_id = response.get("id")
    if response_id is None:
        return None
    if str(response_id) != expected_id:
        raise ToolValidationError(
            "MCP provider "
            f"'{provider_name}' returned an unexpected response id while calling "
            f"'{method}'.",
        )
    return response


def stdio_session_unavailable_message(provider_name: str) -> str:
    return f"MCP provider '{provider_name}' session is not available."


def stdio_send_failure_message(provider_name: str) -> str:
    return (
        f"MCP provider '{provider_name}' session terminated unexpectedly while "
        "sending a request."
    )


def stdio_timeout_message(provider_name: str, method: str) -> str:
    return (
        f"MCP provider '{provider_name}' timed out while waiting for method "
        f"'{method}'."
    )


def stdio_terminated_message(
    provider_name: str,
    *,
    method: str,
    stderr_detail: str,
) -> str:
    detail = (
        redact_mcp_diagnostic(stderr_detail) if stderr_detail else "no stderr output"
    )
    return (
        f"MCP provider '{provider_name}' terminated while waiting for method "
        f"'{method}': {detail}"
    )


__all__ = [
    "parse_stdio_response_line",
    "stdio_message_bytes",
    "stdio_message_text",
    "stdio_send_failure_message",
    "stdio_session_unavailable_message",
    "stdio_terminated_message",
    "stdio_timeout_message",
]
