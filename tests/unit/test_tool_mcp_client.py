from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import patch

from crxzipple.core.config import McpProviderSettings
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.infrastructure import McpHttpClient
from crxzipple.modules.tool.infrastructure.mcp_stdio_async_session import (
    McpStdioAsyncSession,
)
from crxzipple.modules.tool.infrastructure.mcp_stdio_sync_session import (
    McpStdioSyncSession,
)


class _SyncStdin:
    def __init__(self) -> None:
        self.closed = False

    def write(self, value: str) -> None:
        del value

    def flush(self) -> None:
        return

    def close(self) -> None:
        self.closed = True


class _SyncStdout:
    def readline(self) -> str:
        return ""


class _SyncStderr:
    def __init__(self, message: str = "stderr detail") -> None:
        self.message = message

    def read(self) -> str:
        return self.message


class _SyncProcess:
    def __init__(self) -> None:
        self.stdin = _SyncStdin()
        self.stdout = _SyncStdout()
        self.stderr = _SyncStderr()
        self.terminated = False
        self.killed = False
        self.returncode: int | None = None

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        self.returncode = 0
        return self.returncode


class _AsyncStdin:
    def __init__(self) -> None:
        self.closed = False
        self.waited_closed = False

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        self.waited_closed = True


class _AsyncStdout:
    async def readline(self) -> bytes:
        return b""


class _AsyncStderr:
    def __init__(self, message: str = "stderr detail") -> None:
        self.message = message

    async def read(self) -> bytes:
        return self.message.encode("utf-8")


class _AsyncProcess:
    def __init__(self) -> None:
        self.stdin = _AsyncStdin()
        self.stdout = _AsyncStdout()
        self.stderr = _AsyncStderr()
        self.terminated = False
        self.killed = False
        self.returncode: int | None = None

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    async def wait(self) -> int:
        self.returncode = 0
        return self.returncode


class _FakeHttpResponse:
    def __init__(
        self,
        *,
        status_code: int,
        headers: dict[str, str] | None = None,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class McpHttpClientTestCase(unittest.TestCase):
    def test_http_client_initializes_lists_and_calls_tools(self) -> None:
        endpoint = "http://mcp.local/mcp"
        requests: list[dict[str, object]] = []

        def fake_request_url(
            method: str,
            url: str,
            **kwargs: object,
        ) -> _FakeHttpResponse:
            payload = kwargs["json"]
            assert isinstance(payload, dict)
            mcp_method = str(payload.get("method") or "")
            requests.append(
                {
                    "method": method,
                    "url": url,
                    "mcp_method": mcp_method,
                    "headers": kwargs.get("headers"),
                    "timeout": kwargs.get("timeout"),
                },
            )
            if mcp_method == "notifications/initialized":
                return _FakeHttpResponse(
                    status_code=202,
                    headers={"Mcp-Session-Id": "session-1"},
                )

            if mcp_method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "serverInfo": {"name": "fake-mcp", "version": "1.0"},
                }
            elif mcp_method == "tools/list":
                result = {
                    "tools": [
                        {
                            "name": "echo",
                            "title": "Echo",
                            "inputSchema": {"type": "object"},
                        },
                    ],
                }
            elif mcp_method == "tools/call":
                result = {
                    "content": [
                        {
                            "type": "text",
                            "text": payload.get("params", {})
                            .get("arguments", {})
                            .get("message"),
                        },
                    ],
                }
            else:
                result = {}

            return _FakeHttpResponse(
                status_code=200,
                headers={"Mcp-Session-Id": "session-1"},
                text=json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": payload.get("id"),
                        "result": result,
                    },
                ),
            )

        client = McpHttpClient(
            McpProviderSettings(
                name="browser",
                transport="http",
                endpoint_url=endpoint,
                timeout_seconds=2,
            ),
        )

        with patch(
            "crxzipple.modules.tool.infrastructure.mcp_http_client.request_url",
            side_effect=fake_request_url,
        ):
            tools = client.list_tools()
            result = client.call_tool(tool_name="echo", arguments={"message": "hello"})
            client.close()

        self.assertEqual([tool["name"] for tool in tools], ["echo"])
        self.assertEqual(result["content"][0]["text"], "hello")
        self.assertEqual(
            [request["mcp_method"] for request in requests],
            [
                "initialize",
                "notifications/initialized",
                "tools/list",
                "tools/call",
            ],
        )
        self.assertNotIn(
            "Mcp-Session-Id",
            requests[0]["headers"],
        )
        for request in requests[1:]:
            self.assertEqual(request["headers"]["Mcp-Session-Id"], "session-1")

    def test_http_client_redacts_transport_failure_diagnostics(self) -> None:
        client = McpHttpClient(
            McpProviderSettings(
                name="browser",
                transport="http",
                endpoint_url="http://mcp.local/mcp",
                timeout_seconds=2,
            ),
        )

        def fake_request_url(
            method: str,
            url: str,
            **kwargs: object,
        ) -> _FakeHttpResponse:
            del method, url, kwargs
            raise RuntimeError(
                "failed http://user:raw-password@mcp.local/mcp?token=raw-query"
                "#access_token=raw-fragment-token&state=ok "
                "Authorization: Bearer raw-bearer-token",
            )

        with patch(
            "crxzipple.modules.tool.infrastructure.mcp_http_client.request_url",
            side_effect=fake_request_url,
        ):
            with self.assertRaises(ToolValidationError) as error:
                client.list_tools()

        message = str(error.exception)
        self.assertNotIn("raw-password", message)
        self.assertNotIn("raw-query", message)
        self.assertNotIn("raw-fragment-token", message)
        self.assertNotIn("raw-bearer-token", message)
        self.assertIn("user:redacted@mcp.local", message)
        self.assertIn("token=redacted", message)
        self.assertIn("access_token=redacted", message)
        self.assertIn("Authorization: Bearer redacted", message)

    def test_http_client_redacts_jsonrpc_error_message(self) -> None:
        endpoint = "http://mcp.local/mcp"

        def fake_request_url(
            method: str,
            url: str,
            **kwargs: object,
        ) -> _FakeHttpResponse:
            del method, url
            payload = kwargs["json"]
            assert isinstance(payload, dict)
            mcp_method = str(payload.get("method") or "")
            if mcp_method == "notifications/initialized":
                return _FakeHttpResponse(
                    status_code=202,
                    headers={"Mcp-Session-Id": "session-1"},
                )
            if mcp_method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "serverInfo": {"name": "fake-mcp", "version": "1.0"},
                }
                return _FakeHttpResponse(
                    status_code=200,
                    headers={"Mcp-Session-Id": "session-1"},
                    text=json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": payload.get("id"),
                            "result": result,
                        },
                    ),
                )
            return _FakeHttpResponse(
                status_code=200,
                headers={"Mcp-Session-Id": "session-1"},
                text=json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": payload.get("id"),
                        "error": {
                            "message": (
                                "tool failed token=raw-jsonrpc-token "
                                "Authorization: Bearer raw-jsonrpc-bearer "
                                '{"api_key":"raw-jsonrpc-api-key"}'
                            ),
                        },
                    },
                ),
            )

        client = McpHttpClient(
            McpProviderSettings(
                name="browser",
                transport="http",
                endpoint_url=endpoint,
                timeout_seconds=2,
            ),
        )

        with patch(
            "crxzipple.modules.tool.infrastructure.mcp_http_client.request_url",
            side_effect=fake_request_url,
        ):
            with self.assertRaises(ToolValidationError) as error:
                client.list_tools()

        message = str(error.exception)
        self.assertNotIn("raw-jsonrpc-token", message)
        self.assertNotIn("raw-jsonrpc-bearer", message)
        self.assertNotIn("raw-jsonrpc-api-key", message)
        self.assertIn("token=redacted", message)
        self.assertIn("Authorization: Bearer redacted", message)
        self.assertIn('"api_key":"redacted"', message)


class McpStdioLifecycleTestCase(unittest.TestCase):
    def test_sync_session_redacts_command_start_failure_diagnostics(self) -> None:
        session = McpStdioSyncSession(
            McpProviderSettings(
                name="local",
                command=(
                    "fake-mcp",
                    "--token=raw-command-token",
                    "Authorization: Bearer raw-command-bearer",
                ),
                timeout_seconds=1,
            ),
        )

        with patch(
            "crxzipple.modules.tool.infrastructure.mcp_stdio_processes.subprocess.Popen",
            side_effect=OSError(
                "spawn failed token=raw-error-token "
                "Authorization: Bearer raw-error-bearer",
            ),
        ):
            with self.assertRaises(ToolValidationError) as error:
                session._start_process_locked()

        message = str(error.exception)
        self.assertNotIn("raw-command-token", message)
        self.assertNotIn("raw-command-bearer", message)
        self.assertNotIn("raw-error-token", message)
        self.assertNotIn("raw-error-bearer", message)
        self.assertIn("token=redacted", message)
        self.assertIn("Authorization: Bearer redacted", message)

    def test_sync_session_closes_process_when_response_times_out(self) -> None:
        process = _SyncProcess()
        session = McpStdioSyncSession(
            McpProviderSettings(
                name="local",
                command=("fake-mcp",),
                timeout_seconds=1,
            ),
        )
        session._process = process
        session._initialized = True

        with patch(
            "crxzipple.modules.tool.infrastructure.mcp_stdio_sync_session.select.select",
            return_value=([], [], []),
        ):
            with self.assertRaisesRegex(
                ToolValidationError,
                "timed out while waiting for method 'tools/list'",
            ):
                session._read_response_locked(
                    expected_id="request-1",
                    method="tools/list",
                )

        self.assertTrue(process.stdin.closed)
        self.assertTrue(process.terminated)
        self.assertFalse(process.killed)
        self.assertIsNone(session._process)
        self.assertFalse(session._initialized)

    def test_sync_session_redacts_stderr_when_server_exits(self) -> None:
        process = _SyncProcess()
        process.stderr = _SyncStderr(
            "server exited token=raw-stderr-token "
            "Authorization: Bearer raw-stderr-bearer",
        )
        session = McpStdioSyncSession(
            McpProviderSettings(
                name="local",
                command=("fake-mcp",),
                timeout_seconds=1,
            ),
        )
        session._process = process
        session._initialized = True

        with patch(
            "crxzipple.modules.tool.infrastructure.mcp_stdio_sync_session.select.select",
            return_value=([process.stdout], [], []),
        ):
            with self.assertRaises(ToolValidationError) as error:
                session._read_response_locked(
                    expected_id="request-1",
                    method="tools/list",
                )

        message = str(error.exception)
        self.assertNotIn("raw-stderr-token", message)
        self.assertNotIn("raw-stderr-bearer", message)
        self.assertIn("token=redacted", message)
        self.assertIn("Authorization: Bearer redacted", message)
        self.assertTrue(process.stdin.closed)
        self.assertTrue(process.terminated)
        self.assertIsNone(session._process)
        self.assertFalse(session._initialized)

    def test_async_session_redacts_command_start_failure_diagnostics(self) -> None:
        session = McpStdioAsyncSession(
            McpProviderSettings(
                name="local",
                command=(
                    "fake-mcp",
                    "--token=raw-async-command-token",
                    "Authorization: Bearer raw-async-command-bearer",
                ),
                timeout_seconds=1,
            ),
        )

        async def _start() -> None:
            await session._start_process_locked()

        with patch(
            "crxzipple.modules.tool.infrastructure.mcp_stdio_processes.asyncio.create_subprocess_exec",
            side_effect=OSError(
                "spawn failed token=raw-async-error-token "
                "Authorization: Bearer raw-async-error-bearer",
            ),
        ):
            with self.assertRaises(ToolValidationError) as error:
                asyncio.run(_start())

        message = str(error.exception)
        self.assertNotIn("raw-async-command-token", message)
        self.assertNotIn("raw-async-command-bearer", message)
        self.assertNotIn("raw-async-error-token", message)
        self.assertNotIn("raw-async-error-bearer", message)
        self.assertIn("token=redacted", message)
        self.assertIn("Authorization: Bearer redacted", message)

    def test_async_session_closes_process_when_server_exits(self) -> None:
        process = _AsyncProcess()
        session = McpStdioAsyncSession(
            McpProviderSettings(
                name="local",
                command=("fake-mcp",),
                timeout_seconds=1,
            ),
        )
        session._process = process
        session._initialized = True

        async def _read_response() -> None:
            await session._read_response_locked(
                expected_id="request-1",
                method="tools/list",
            )

        with self.assertRaisesRegex(
            ToolValidationError,
            "terminated while waiting for method 'tools/list': stderr detail",
        ):
            asyncio.run(_read_response())

        self.assertTrue(process.stdin.closed)
        self.assertTrue(process.stdin.waited_closed)
        self.assertTrue(process.terminated)
        self.assertFalse(process.killed)
        self.assertIsNone(session._process)
        self.assertFalse(session._initialized)

    def test_async_session_redacts_stderr_when_server_exits(self) -> None:
        process = _AsyncProcess()
        process.stderr = _AsyncStderr(
            "server exited token=raw-async-stderr-token "
            "Authorization: Bearer raw-async-stderr-bearer",
        )
        session = McpStdioAsyncSession(
            McpProviderSettings(
                name="local",
                command=("fake-mcp",),
                timeout_seconds=1,
            ),
        )
        session._process = process
        session._initialized = True

        async def _read_response() -> None:
            await session._read_response_locked(
                expected_id="request-1",
                method="tools/list",
            )

        with self.assertRaises(ToolValidationError) as error:
            asyncio.run(_read_response())

        message = str(error.exception)
        self.assertNotIn("raw-async-stderr-token", message)
        self.assertNotIn("raw-async-stderr-bearer", message)
        self.assertIn("token=redacted", message)
        self.assertIn("Authorization: Bearer redacted", message)
        self.assertTrue(process.stdin.closed)
        self.assertTrue(process.stdin.waited_closed)
        self.assertTrue(process.terminated)
        self.assertFalse(process.killed)
        self.assertIsNone(session._process)
        self.assertFalse(session._initialized)


if __name__ == "__main__":
    unittest.main()
