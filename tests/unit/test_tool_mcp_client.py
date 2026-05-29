from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import unittest

from crxzipple.core.config import McpProviderSettings
from crxzipple.modules.tool.infrastructure import McpHttpClient


class _McpHttpHandler(BaseHTTPRequestHandler):
    methods: list[str] = []

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        method = str(payload.get("method") or "")
        self.__class__.methods.append(method)

        if method == "notifications/initialized":
            self.send_response(202)
            self.end_headers()
            return

        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "serverInfo": {"name": "fake-mcp", "version": "1.0"},
            }
        elif method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "echo",
                        "title": "Echo",
                        "inputSchema": {"type": "object"},
                    },
                ],
            }
        elif method == "tools/call":
            result = {
                "content": [
                    {
                        "type": "text",
                        "text": payload.get("params", {}).get("arguments", {}).get("message"),
                    },
                ],
            }
        else:
            result = {}

        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": payload.get("id"),
                "result": result,
            },
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Mcp-Session-Id", "session-1")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class McpHttpClientTestCase(unittest.TestCase):
    def test_http_client_initializes_lists_and_calls_tools(self) -> None:
        _McpHttpHandler.methods = []
        server = ThreadingHTTPServer(("127.0.0.1", 0), _McpHttpHandler)
        thread = threading.Thread(
            target=lambda: server.serve_forever(poll_interval=0.01),
            daemon=True,
        )
        thread.start()
        endpoint = f"http://127.0.0.1:{server.server_port}/mcp"
        client = McpHttpClient(
            McpProviderSettings(
                name="browser",
                transport="http",
                endpoint_url=endpoint,
                timeout_seconds=2,
            ),
        )

        try:
            tools = client.list_tools()
            result = client.call_tool(tool_name="echo", arguments={"message": "hello"})
        finally:
            client.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=1)

        self.assertEqual([tool["name"] for tool in tools], ["echo"])
        self.assertEqual(result["content"][0]["text"], "hello")
        self.assertEqual(
            _McpHttpHandler.methods,
            [
                "initialize",
                "notifications/initialized",
                "tools/list",
                "tools/call",
            ],
        )


if __name__ == "__main__":
    unittest.main()
